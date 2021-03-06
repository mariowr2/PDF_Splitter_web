#!/bin/bash
mkdir static/served_files
mkdir static/uploaded_files
sudo apt-get install python-pip
sudo pip install virtualenv
virtualenv virtual_env --python=/usr/bin/python2.7
source virtual_env/bin/activate
sudo apt install poppler-utils
sudo apt-get install libjpeg8-dev
sudo apt-get install python-systemd
pip install -r requirements.txt
./download-opencv.sh
make
rm opencv-2.4.13.5.zip