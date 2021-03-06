## Author: Mario Mendez Diaz

from pdf2image import convert_from_path
import PIL
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus.flowables import Image
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from backports import tempfile
import systemd
import StringIO
import cv2
import numpy
import sys
import os
import shutil
import logging
import argparse

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())


def find_box_using_opencv(image, min_width, min_height, max_width, max_height, debug):	#find a slide/box in an image (should only pass images that contain a single slide)
	lower_bound_pixel = 0 #values used in colour thresholding
	upper_bound_pixel = 5
	opencv_image = numpy.array(image) # convert to open cv image

	#open cv tings start
	grayscale_img = cv2.cvtColor(opencv_image, cv2.COLOR_RGB2GRAY)

	mask = cv2.inRange(grayscale_img, lower_bound_pixel,upper_bound_pixel) #find black elements (assuming black boxes)
	contours = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2]#find contours in mask

	if len(contours) > 0:
		slide_coords = max(contours, key = cv2.contourArea) #get the biggest contour
		if len(slide_coords) == 4: #ensure precisely 4 coords, slides are squares

				if debug:
					cv2.drawContours(opencv_image, slide_coords, -1, (0,255,0), 3)
					cv2.imwrite("contour.png", opencv_image)

				slide_found_width = (slide_coords[2][0])[0] - (slide_coords[0][0])[0] #get width and heihgt
				slide_found_height = (slide_coords[2][0])[1] - (slide_coords[0][0])[1]

				#ensure found width and height is between allowed bounds
				if(slide_found_width > min_width and slide_found_width < max_width and 
					slide_found_height > min_height and slide_found_height < max_height):
					return slide_coords
	else:
		return None

#used when finding 4 slides
def find_upper_left_slide(image, pdf_name, min_width, min_height, max_width, max_height):	#use the upper left quarter of an image to find the coordinates of a single slide/box

	area = (0,0,image.size[0]/2, image.size[1]/2) # coordinates of upper left quadrant of image)
	image_quadrant = image.crop(area) 

	slide_box_coordinates = find_box_using_opencv(image_quadrant, min_width, min_height, max_width, max_height, False) #find the cords of the slide in the upper left quadrant

	if slide_box_coordinates is None:
		logger.warning("Failed to find slide in left upper quadrant in file "+pdf_name)
		return None
	else:
		logger.warning("Success finding slide in left upper quadrant in file "+pdf_name)
		return slide_box_coordinates


#return the three biggest 4-point contours given a list of contours
def get_three_largest_contours(contours):
	
	three_largest_contours = []
	indexes_with_more_than_four_points = []

	# get the indexes of contours with more than 4 points, since they are not slides! 
	for i in range(0,len(contours)-1):
		if len(contours[i]) > 4:
			indexes_with_more_than_four_points.append(i)


	#delete the indexes of the contours
	for index in indexes_with_more_than_four_points:
		if index < len(contours):
			del contours[index]

	#sort the remaining list by area and append the first three contours
	sorted_contours = sorted(contours, key=lambda x: cv2.contourArea(x))
	three_largest_contours.append(sorted_contours[0])
	three_largest_contours.append(sorted_contours[1])
	three_largest_contours.append(sorted_contours[2])	

	return three_largest_contours


#return the contour coordinates of all 3 slides in the left half of the image
def find_left_slides_using_opencv(image, min_width, min_height, max_width, max_height):
	
	lower_bound_pixel = 0 #values used in colour thresholding
	upper_bound_pixel = 5
	opencv_image = numpy.array(image) # convert to open cv image
	second_image = opencv_image.copy()

	min_slide_area = min_width * min_height
	max_slide_area = max_width * max_height

	#open cv tings start
	grayscale_img = cv2.cvtColor(opencv_image, cv2.COLOR_RGB2GRAY)

	mask = cv2.inRange(grayscale_img, lower_bound_pixel,upper_bound_pixel) #find black elements (assuming black boxes)
	contours = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2]#find contours in mask

	if len(contours) > 2: #make sure at least 3 contours were found in the image
		three_largest_contours = get_three_largest_contours(contours)  #get the three largest contours
		

		#check that the returned contours are inside the allowed bounds UGLY HACK
		slides_inside_bounds = (cv2.contourArea(three_largest_contours[0]) > min_slide_area and cv2.contourArea(three_largest_contours[0]) < max_slide_area)
		slides_inside_bounds = slides_inside_bounds and (cv2.contourArea(three_largest_contours[1]) > min_slide_area and cv2.contourArea(three_largest_contours[1]) < max_slide_area)
		slides_inside_bounds = slides_inside_bounds and (cv2.contourArea(three_largest_contours[2]) > min_slide_area and cv2.contourArea(three_largest_contours[2]) < max_slide_area)
		
		if slides_inside_bounds:
			return three_largest_contours
		else:
			return None
	else:
		return None #return empty list


#used when finding 6 slides total, returns the coordinates of all slides in the left half of the image
def find_left_slides(image, pdf_name, min_width, min_height, max_width, max_height):
	area = (0,0,image.size[0]/2, image.size[1])
	image_quadrant = image.crop(area)
	left_slide_coordinates = find_left_slides_using_opencv(image_quadrant, min_width, min_height, max_width, max_height)
	return left_slide_coordinates





def calculate_all_slides_coords(upper_left_coords, pdf_size): #calculate one pair of coordinates for all boxes AND width and height of each box

	quadrant_size = (pdf_size[0]/2, pdf_size[1]/2)	
	box_width = upper_left_coords[2][0][0] - upper_left_coords[0][0][0]
	box_height = upper_left_coords[2][0][1] - upper_left_coords[0][0][1]

	#first get measurements relative to the distance of the found box and the edges of the quadrants
	left_x_distance = upper_left_coords[0][0][0]#(x coordinate of left edge)
	right_x_distance = quadrant_size[0] - upper_left_coords[2][0][0]# difference between x corordinate of right edge and edge of quadrant

	y_top_distance = upper_left_coords[0][0][1]# distance from top of box to upper edge of quadrant
	y_lower_distance = quadrant_size[1] - upper_left_coords[2][0][1] # difference between y coordinate of lower edge and the height of the quadrany

	# coordinates of upper left box
	upper_left_quadrant_x = upper_left_coords[0][0][0] #upper left box first
	upper_left_quadrant_y = upper_left_coords[0][0][1]
	
	boxes_coords = [[upper_left_quadrant_x, upper_left_quadrant_y]] # add upper left box

	# coordinates of upper right box
	upper_right_cuadrant_x = quadrant_size[0] + right_x_distance #x coord of upper right quadrant, upper left edge
	upper_right_cuadrant_y = y_top_distance #y coord of upper right quadrant , upper left edge
	boxes_coords.insert(1,[upper_right_cuadrant_x, upper_right_cuadrant_y])

	#coordinates of lower left box
	lower_left_cuadrant_x = upper_left_quadrant_x
	lower_left_cuadrant_y = quadrant_size[1] + y_lower_distance
	boxes_coords.insert(2,[lower_left_cuadrant_x,lower_left_cuadrant_y])

	#coordinates of lower right box
	lower_right_cuadrant_x = upper_right_cuadrant_x
	lower_right_cuadrant_y = lower_left_cuadrant_y
	boxes_coords.insert(3,[lower_right_cuadrant_x, lower_right_cuadrant_y])

	return boxes_coords, (box_width, box_height)


#calculate the rest of the coordinates using the coordinates already acquired
def calculate_remaining_slides_coordinates(left_half_slides_coords, pdf_size):

	left_boxes_coords = None # stores the top left corner of all 6 slides in the document
	right_boxes_coords = None

	quadrant_size = (pdf_size[0]/2, pdf_size[1])

	#calculate the width and height for all slides
	box_width = left_half_slides_coords[0][3][0][0] - left_half_slides_coords[0][0][0][0]
	box_height = left_half_slides_coords[0][2][0][1] - left_half_slides_coords[0][0][0][1]

	#calculate the distance from each slide to right borders of the document
	box_distance_right_border = quadrant_size[0] - left_half_slides_coords[0][3][0][0]


	#first dump all top left coords of the 3 slides that have been found already
	left_boxes_coords = [[ left_half_slides_coords[0][0][0][0], left_half_slides_coords[0][0][0][1]]]
	left_boxes_coords.insert(1, [left_half_slides_coords[1][0][0][0], left_half_slides_coords[1][0][0][1]])
	left_boxes_coords.insert(2, [left_half_slides_coords[2][0][0][0], left_half_slides_coords[2][0][0][1]])


	#sort coordinates in ascending order depending on their y coordinate! ; very important
	left_boxes_coords = sorted(left_boxes_coords,key=lambda l:l[1])

	
	#now calculate the coordinates on the other half of the image

	#first top right slide, only need to calculate the x once!
	
	#top_right_slide_x = left_boxes_coords[0][0] + box_width +(2 * box_distance_right_border) 
	top_right_slide_x = pdf_size[0]/2 + box_distance_right_border
	top_right_slide_y = left_boxes_coords[0][1]
	right_boxes_coords = [[top_right_slide_x, top_right_slide_y]]

	#middle right slide
	middle_right_slide_y = left_boxes_coords[1][1]
	right_boxes_coords.insert(1, [top_right_slide_x, middle_right_slide_y])

	#bottom right slide
	bottom_right_slide_y = left_boxes_coords[2][1]
	right_boxes_coords.insert(2, [top_right_slide_x, bottom_right_slide_y])	

	return left_boxes_coords, right_boxes_coords, (box_width, box_height)


def extract_images_from_pdf(pdf_file_path, dir_path):	# use the pdf2image library to convert every page in the pdf to an image
	try:
		images = convert_from_path(pdf_file_path, output_folder=dir_path)
	except Exception as err:
		logger.error("exceptio is "+err)
		logger.error("Error on pdf \""+pdf_file_path+"\",pdf2 img failed to convert pdf to images") #catch exception
		raise Exception("Error on pdf \""+pdf_file_path+"\",pdf2 img failed to convert pdf to images")
	return images


def verify_slide(pdf_image,slide_coords,slide_size, slide_number): #verify the pixels found with open cv and ensure these have black pixels at coordinates

	opencv_image = numpy.array(pdf_image) # convert to open cv image
	grayscale_img = cv2.cvtColor(opencv_image, cv2.COLOR_RGB2GRAY)
	correct_coords = [False, False, False, False] #represents if the coords of each slide truly represent its location

	#check that all coordinates have a black pixel in the image
	#black pixel means that the black edge of a slide is at the coordinates
	for i in range(0,slide_number):
		if(grayscale_img.item(slide_coords[i][1],slide_coords[i][0]) == 0) :   #check left top corner
			if(grayscale_img.item((slide_coords[i][1] + slide_size[1]) -1,(slide_coords[i][0] + slide_size[0] -1 )) == 0):
				correct_coords[i] = True


	if slide_number == 4:
		if(correct_coords[0] and correct_coords[1] and correct_coords[2] and correct_coords[3]): #if all coords are accurate then just return a single true
			return [True]
		else:
			return correct_coords
	if slide_number == 3:
		if(correct_coords[0] and correct_coords[1] and correct_coords[2]):
			return [True]
		else:
			return correct_coords
	else:
		return correct_coords


	
def crop_images(images_dir, cropped_imgs_dir_dst, coords, size):  # crop all images once the coordinates are known, crop only the "individual slides"
	assert len(list_files_in_dir(images_dir)) > 0
	filename_counter = 0
	images_files = list_files_in_dir(images_dir)
	for image_filename in sort_file_list_uuid(images_files):
		image = PIL.Image.open(os.path.join(images_dir, image_filename))
		for i in range(0, len(coords)):
			crop_area = (coords[i][0], coords[i][1], coords[i][0] + size[0], coords[i][1] + size[1]) # area is xy coords, plus width and height
			cropped_image = image.crop(crop_area)
			cropped_image.save(os.path.join(cropped_imgs_dir_dst, str(filename_counter)+".ppm"), 'PPM')
			filename_counter+=1



def create_new_document(filename, slides_imgs_dir, output_destination): #create the output document
	assert len(list_files_in_dir(slides_imgs_dir)) > 0
	output_filename = "new_"+filename
	working_dir_path = output_destination+output_filename # get full path of file
	c = canvas.Canvas(working_dir_path, pagesize=letter) # create pdf document

	slide_imgs_files = list_files_in_dir(slides_imgs_dir)
	# save all images into pdf, one page at a time
	for slide_filename in sort_file_list_indexed_ppm(slide_imgs_files):
		slide = PIL.Image.open(os.path.join(slides_imgs_dir, slide_filename))
		side_im = slide
		side_im_data = StringIO.StringIO()
		side_im.save(side_im_data, format='png')
		side_im_data.seek(0)
		side_out = ImageReader(side_im_data)
		c.drawImage(side_out,50,250)
		c.showPage()
	c.save() # save the output!
	return output_filename

def resize_images(cropped_imgs_dir, resized_imgs_dst_dir): #resize all images before they are included in the output	
	assert len(list_files_in_dir(cropped_imgs_dir)) > 0
	basewidth = 500   #moidy this value to change image size!
	ref_img = get_reference_image(cropped_imgs_dir)
	width = (basewidth/float(ref_img.size[0]))
	height = int((float(ref_img.size[1]) * float(width)))

	cropped_imgs_files = list_files_in_dir(cropped_imgs_dir)

	for image_filename in sort_file_list_indexed_ppm(cropped_imgs_files):
		image = PIL.Image.open(os.path.join(cropped_imgs_dir, image_filename))
		image = image.resize((basewidth, height), PIL.Image.ANTIALIAS)
		image.save(os.path.join(resized_imgs_dst_dir, image_filename), 'PPM')


def assert_document_dimensions(width, height):
	orientation = False
	if( width == 1700 and height == 2200):
		orientation = True
	elif( width == 2200 or height == 1700):
		orientation = True
	return orientation

#merge list of coordinates
def merge_slides_from_halves(left_side, right_side, mode):
	merged_coordinates = None
	#mode 1 has ordering: [top_left, right_left, middle_left, middle_right, bottom_left, bottom_right]
	#mode 2 has ordering: [top_left, middle_left, bottom_left, top_right, middle_right, bottom_right]
	if mode == 1:
		merged_coordinates = [left_side[0],  left_side[1],  left_side[2],  right_side[0], right_side[1], right_side[2]]
	else:
		merged_coordinates = [left_side[0],  right_side[0],  left_side[1],  right_side[1], left_side[2], right_side[2]]
	return merged_coordinates

#zipper merge two lists, hopefully staying in bounds
def merge_images(list_one, list_two):
	merged_list = []
	for i in range(0, len(list_one)):
		merged_list.append(list_one[i])
		merged_list.append(list_two[i])
	return merged_list

#=============================================================
# MAIN PROCESSING FOR EACH KIND OF PDF
#=============================================================
def process_2_slide_pdf(pdf_as_img_dir_path, pdf_name, input_location, output_destination, reference_img, half_imgs_dir_path, img_crop_dir_path, img_resize_dir_path):
	min_slide_width = 200
	min_slide_height = 200
	max_slide_width = 1050
	max_slide_height = 840

	#first crop the image in the two halves
	area_upper_half= (0,0,reference_img.size[0], reference_img.size[1]/2) # coordinates of upper left quadrant of image)
	area_lower_half = (0, reference_img.size[1]/2, reference_img.size[0], reference_img.size[1])
	
	upper_image_half = reference_img.crop(area_upper_half)
	lower_image_half = reference_img.crop(area_lower_half) 	

	upper_box_coordinates = find_box_using_opencv(upper_image_half, min_slide_width, min_slide_height, max_slide_width, max_slide_height, False) # attempt to find an individual slides so that slides can be centered in their own page
	lower_box_coordinates = find_box_using_opencv(lower_image_half, min_slide_width, min_slide_height, max_slide_width, max_slide_height, False) # attempt to find an individual slides so that slides can be centered in their own page

	if upper_box_coordinates is not None and lower_box_coordinates is not None:

		#calculate width and height for both slides
		upper_slide_width = upper_box_coordinates[2][0][0] - upper_box_coordinates[0][0][0]
		upper_slide_height = upper_box_coordinates[2][0][1] - upper_box_coordinates[0][0][1]

		lower_slide_width = lower_box_coordinates[2][0][0] - lower_box_coordinates[0][0][0]
		lower_slide_height = lower_box_coordinates[2][0][1] - lower_box_coordinates[0][0][1]


		#get the top left coordinate of the slide for both upper and lower
		upper_slide_x = upper_box_coordinates[0][0][0]  
		upper_slide_y = upper_box_coordinates[0][0][1]

		lower_slide_x = lower_box_coordinates[0][0][0]  
		lower_slide_y = lower_box_coordinates[0][0][1]

		#crop all images in half, save each of these halves to a temporary directory
		filename_counter = 0
		assert len(list_files_in_dir(pdf_as_img_dir_path)) > 0
		pdf_as_img_filenames = list_files_in_dir(pdf_as_img_dir_path) 
		for image_filename in sort_file_list_uuid(pdf_as_img_filenames):
			image = PIL.Image.open(os.path.join(pdf_as_img_dir_path, image_filename)) #open the image from the temp dir containing the whole doc as a imgs
			
			#crop the top and save it to the temp dir
			upper_img_half = image.crop(area_upper_half)
			upper_img_half.save(os.path.join(half_imgs_dir_path, 'a-b-c-d-e-'+str(filename_counter)+'.ppm'), 'PPM') #a-b-c.. is an ugly hack for filenames to look as crop_images expects them
			filename_counter+=1
			#crop the bottom and save it to the temp dir
			lower_img_half = image.crop(area_lower_half)
			lower_img_half.save(os.path.join(half_imgs_dir_path, 'a-b-c-d-e-'+str(filename_counter)+'.ppm'), 'PPM')
			filename_counter+=1

		#crop and resize, seperately , merge in the end
		crop_images(half_imgs_dir_path, img_crop_dir_path,[[upper_slide_x, upper_slide_y]], (upper_slide_width, upper_slide_height))
		resize_images(img_crop_dir_path, img_resize_dir_path)
		output_document_name = create_new_document(pdf_name, img_resize_dir_path, output_destination)
		return output_document_name
	else:
		logger.error("Failed to find slides in document.")
		raise Exception("Failed to find slides in document.")



def process_6_slide_pdf(pdf_as_img_dir_path, pdf_name, input_location, output_destination, splitting_mode, reference_img, img_crop_dir_path, img_resize_dir_path):
	min_slide_width = 50
	min_slide_height = 50
	max_slide_width = 1050
	max_slide_height = 840
	logger.info("Doing 6 slides, mode "+str(splitting_mode))
	#get the coordinates for all of the slides in the left half of the iamge
	left_slides_coords = find_left_slides(reference_img, pdf_name, min_slide_width, min_slide_height, max_slide_width, max_slide_height)	
	if left_slides_coords:
		left_side_slide_coords, right_side_slide_coords, slide_size = calculate_remaining_slides_coordinates(left_slides_coords, reference_img.size)
		combined_slides = merge_slides_from_halves(left_side_slide_coords, right_side_slide_coords, splitting_mode)	
		crop_images(pdf_as_img_dir_path, img_crop_dir_path, combined_slides, slide_size)
		resize_images(img_crop_dir_path, img_resize_dir_path)
		output_document_name = create_new_document(pdf_name, img_resize_dir_path, output_destination) 
		return output_document_name
	else:
		logger.error("Failed to find 3 slides on the image.")
		raise Exception("Failed to find 3 slides on the image.")

def process_4_slide_pdf(pdf_as_img_dir_path, pdf_name, input_location, output_destination, reference_img, img_crop_dir_path, img_resize_dir_path):
	min_slide_width = 200
	min_slide_height = 200
	max_slide_width = 1050
	max_slide_height = 840
	logger.info("Doing 4 slides")
	upper_left_box_coordinates = find_upper_left_slide(reference_img, pdf_name, min_slide_width, min_slide_height, max_slide_width, max_slide_height) # attempt to find an individual slides so that slides can be centered in their own page
	if(upper_left_box_coordinates is not None): #only proceed if coordinates were found
		slide_coordinates, slide_dimentions = calculate_all_slides_coords(upper_left_box_coordinates, reference_img.size) #get all cords from all slides per image
		logger.info("All slides found successfully in " + pdf_name)
		crop_images(pdf_as_img_dir_path, img_crop_dir_path, slide_coordinates, slide_dimentions)
		resize_images(img_crop_dir_path, img_resize_dir_path)
		output_document_name = create_new_document(pdf_name, img_resize_dir_path, output_destination) # DOCUMENT PROCESSED SUCCESFULLY!
		return output_document_name
	else:
		logger.error("Failed to find individual slide.")
		raise Exception("Failed to find individual slide.")

def get_filename_int_identifier_from_uuid(filename):
	dash_separated_filename = filename.split("-")
	assert len(dash_separated_filename) > 0
	last_element = dash_separated_filename[len(dash_separated_filename) - 1] # string shoud look like '23.ppm'
	last_element_int = last_element[:len(last_element) - 4] # remove the .ppm file extension
	return int(last_element_int)

#sorts (ascending) a list of filenames of the form '98d0b582-5b10-4377-8edc-39079905d9f0-3.ppm', '98d0b582-5b10-4377-8edc-39079905d9f0-1.ppm...
def sort_file_list_uuid(file_list):
	return sorted(file_list, key=lambda filename: get_filename_int_identifier_from_uuid(filename))

def get_filename_int_identifier_from_indexed_ppm(filename):
	file_index = filename[:len(filename) - 4] # remove the .ppm file extension
	return int(file_index)

# sorts (ascending) a list of filenames of the form ['6.ppm', '11.ppm', '5.ppm', '1.ppm', '9.ppm']..
def sort_file_list_indexed_ppm(file_list):
	return sorted(file_list, key=lambda filename: get_filename_int_identifier_from_indexed_ppm(filename))

def list_files_in_dir(dir_path):
	file_list = [f for f in os.listdir(dir_path) if os.path.isfile(os.path.join(dir_path, f))]
	return file_list

def img_extraction_success(dir_path):
	extracted_img_filenames = list_files_in_dir(dir_path)
	return len(extracted_img_filenames) > 0

def get_reference_image(dir_path):
	first_img_path = os.path.join(dir_path, list_files_in_dir(dir_path)[0])
	first_img = PIL.Image.open(first_img_path)
	return first_img

def process_pdf(pdf_name, input_location, output_destination, splitting_mode, pdf_as_img_dir_path, half_imgs_dir_path, img_crop_dir_path, img_resize_dir_path):
	extract_images_from_pdf(input_location+pdf_name, pdf_as_img_dir_path) # get all pages in pdf as images
	if img_extraction_success(pdf_as_img_dir_path) is True: #verify that the image extraction was successful
		reference_img = get_reference_image(pdf_as_img_dir_path)
		correct_dimensions = assert_document_dimensions(reference_img.size[0], reference_img.size[1]) # get size of document
		if correct_dimensions and splitting_mode ==0:
			return process_4_slide_pdf(pdf_as_img_dir_path, pdf_name, input_location, output_destination, reference_img, img_crop_dir_path, img_resize_dir_path)
		if correct_dimensions and (splitting_mode == 1) or (splitting_mode == 2):
			return process_6_slide_pdf(pdf_as_img_dir_path, pdf_name, input_location, output_destination, splitting_mode, reference_img, img_crop_dir_path, img_resize_dir_path)
		if correct_dimensions and splitting_mode == 3:
			return process_2_slide_pdf(pdf_as_img_dir_path, pdf_name, input_location, output_destination, reference_img, half_imgs_dir_path, img_crop_dir_path, img_resize_dir_path)
		else:
			logger.error("Incorrect dimensions or incorrect mode")
			raise Exception("Incorrect dimensions or incorrect mode")
	else:
		logger.error("Failed to extract images from pdf")
		raise Exception("Failed to extract images from pdf")
	logger.error("could not find any imatges")
	raise Exception("could not find any imatges")

def get_args(args_list):
	parser = argparse.ArgumentParser()
	parser.add_argument('-f', '--filename', type=str)
	parser.add_argument('-i', '--input_location', type=str)
	parser.add_argument('-o', '--output_location', type=str)
	parser.add_argument('-m', '--mode', type=int)
	return parser.parse_args()
	
def main(args):
	args = get_args(args)
	failed = False
	try:
		pdf_as_img_dir_path = tempfile.mkdtemp()
		half_imgs_dir_path = tempfile.mkdtemp()
		img_crop_dir_path = tempfile.mkdtemp()
		img_resize_dir_path  = tempfile.mkdtemp()
		return process_pdf(args.filename, args.input_location, args.output_location, args.mode, pdf_as_img_dir_path, half_imgs_dir_path, img_crop_dir_path, img_resize_dir_path)
	except Exception as err:
		logger.error("split_pdf.py failed!")
		logger.error(err)
		failed = True
	finally:
		# delete all the temp files before leaving
		shutil.rmtree(pdf_as_img_dir_path)
		shutil.rmtree(half_imgs_dir_path)
		shutil.rmtree(img_crop_dir_path)
		shutil.rmtree(img_resize_dir_path)
		if failed:
			exit(-1)

	
if __name__ == '__main__':
	main(sys.argv[1:])