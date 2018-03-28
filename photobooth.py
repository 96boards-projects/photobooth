import numpy as np
import cv2
import time
import os
import mraa
import imutils
import _thread
import boto3
from PIL import Image
from pyshorteners import Shortener
from random import *

pressed = False
capture = False
filter_opt = 1
count = randint(1, 100000)

# Initialize V4l2 with CSI interface
os.system("v4l2-ctl -d /dev/video0")

# Initialize video capture for OpenCV
cap = cv2.VideoCapture(0)

# Create main window
cv2.namedWindow('96Boards Photobooth', cv2.WINDOW_NORMAL)
cv2.resizeWindow('96Boards Photobooth', 800, 480)

#Load filter
filter_1 = cv2.imread('moustache.png')
filter_2 = cv2.imread('cowboy_hat.png')
watermark = Image.open('watermark.png')

# Load classifier
detector=cv2.CascadeClassifier('haarcascade_frontalface_default.xml')

s3 = boto3.resource('s3')

def put_moustache_filter(mst, frame, x, y, w, h):
    face_width = w
    face_height = h

    mst_width = int(face_width*0.4166666)+1
    mst_height = int(face_height*0.142857)+1

    mst = cv2.resize(mst,(mst_width,mst_height))

    for i in range(int(0.62857142857*face_height),int(0.62857142857*face_height)+mst_height):
        for j in range(int(0.29166666666*face_width),int(0.29166666666*face_width)+mst_width):
            for k in range(3):
                if mst[i-int(0.62857142857*face_height)][j-int(0.29166666666*face_width)][k] <235:
                    frame[y+i][x+j][k] = mst[i-int(0.62857142857*face_height)][j-int(0.29166666666*face_width)][k]
                                                                                                    
    return frame

def put_hat_filter(hat, frame, x, y, w, h):
    face_width = w
    face_height = h
            
    hat_width = face_width+1
    hat_height = int(0.35*face_height)+1
    
    hat = cv2.resize(hat,(hat_width,hat_height))
                                    
    for i in range(hat_height):
        for j in range(hat_width):
            for k in range(3):
                if hat[i][j][k]<235:
                    frame[y+i-int(0.25*face_height)][x+j][k] = hat[i][j][k]
    return frame

# Helper sub-routine to add text to a frame
def putText(frame, text, x_pos, y_pos, color, size):
    font = cv2.FONT_HERSHEY_SIMPLEX

    cv2.putText(frame, text, (int(x_pos), int(y_pos)), font, size, color, 2)

def upload(image):
    data = open(image, 'rb')
    s3.Bucket('96boards-photobooth').put_object(Key=image, Body=data)

def genqr(url):
    qrcode = 'qrcode.png'
    os.system('qrencode -s %d -o "%s" %s' % (20, qrcode, url))
    return qrcode

def shorten_url(url):
    shortener = Shortener('Tinyurl', timeout=9000)
    return shortener.short(url)

def final_display(qrcode, url):
    # Create a new window for final display
    cv2.namedWindow('Grab Your Image', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Grab Your Image', 800, 480)

    img = cv2.imread('qrcode.png')
    color = (255, 0, 0)
    x_pos = 100
    y_pos = 50
    putText(img, url, x_pos, y_pos, color, 1.3)
    cv2.imshow('Grab Your Image', img)
    cv2.waitKey(10000)
    cv2.destroyWindow('Grab Your Image')

def process_image(text, x, y):
    global capture
    global count

    ret, frame = cap.read()
    frame = imutils.resize(frame, width=250)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = detector.detectMultiScale(gray, 1.1, 5, minSize=(40,40), flags=cv2.CASCADE_SCALE_IMAGE)
    for (x, y, w, h) in faces:
        if filter_opt == 1:
            frame = put_moustache_filter(filter_1, frame, x, y, w, h)
        if filter_opt == 2:
            frame = put_hat_filter(filter_2, frame, x, y, w, h)

    # Once countdown is over, store the captured image
    if capture == True:
        url = "https://s3-ap-southeast-1.amazonaws.com/96boards-photobooth/" + "final/user_" + str(count) + ".png"
        cap_image = "captured/user_" + str(count) + "_captured" + ".jpg"
        cv2.imwrite(cap_image, frame)
        # Apply 96Boards watermark to the captured image
        final_img = apply_watermark(count)
        # Upload image to S3 bucket
        upload(final_img)
        # Generate QR code for the image
        qrcode = genqr(url)
	# Shorten URL
        tinyurl = shorten_url(url)
        # Display image and QR code
        final_display(qrcode, tinyurl)
        count += 1
        capture = False

    cv2.imshow('96Boards Photobooth', frame)

# Helper sub-routine to apply watermark to the captured image
def apply_watermark(count):
    global watermark

    base = Image.open("captured/user_" + str(count) + "_captured" + ".jpg")
    if base.mode != 'RGBA':
        base = base.convert('RGBA')
    layer = Image.new('RGBA', base.size, (0,0,0,0))
    position = (base.size[0] - watermark.size[0], base.size[1] - watermark.size[1])
    layer.paste(watermark, position)
    final_img = "final/user_" + str(count) + ".png"
    Image.composite(layer, base, layer).save(final_img)

    return final_img

def capture_callback(capture_btn):
    global pressed
    pressed = True

def filter_callback(filter_btn):
    global filter_opt
    
    filter_opt += 1
    if filter_opt > 2:
        filter_opt = 1

def countdown(thread, lock):
    lock.acquire()
    global pressed
    global capture

    # Create a new window for countdown
    cv2.namedWindow('Countdown', cv2.WINDOW_NORMAL)
    cv2.moveWindow('Countdown', 300, 140)
    cv2.resizeWindow('Countdown', 150, 150)
    font = cv2.FONT_HERSHEY_SIMPLEX
    color = (255, 255, 255)

    # Give some time for window to initialize
    time.sleep(1)
    for x in range(5, 0, -1):
        # Create a black image
        img = np.zeros((150,150,3), np.uint8)
        textsize = cv2.getTextSize(str(x), font, 1, 2)[0]
        x_pos = (img.shape[1] - textsize[0]) / 2
        y_pos = (img.shape[0] + textsize[1]) / 2
        # Display the countdown
        putText(img, str(x), x_pos, y_pos, color, 1)
        cv2.imshow('Countdown', img)
        cv2.waitKey(10)
        time.sleep(1)

    # Create a dummy black image
    text = "CHEESE"
    img = np.zeros((150,150,3), np.uint8)
    textsize = cv2.getTextSize(text, font, 1, 2)[0]
    color = (255, 255, 255)
    x_pos = (img.shape[1] - textsize[0]) / 2
    y_pos = (img.shape[0] + textsize[1]) / 2
    putText(img, text, x_pos, y_pos, color, 1)
    cv2.imshow('Countdown', img)
    cv2.waitKey(10)
    time.sleep(1)
    cv2.destroyWindow('Countdown')
    time.sleep(1)
    capture = True
    lock.release()

# Initialize Capture button
capture_btn = mraa.Gpio(30)
capture_btn.dir(mraa.DIR_IN)
capture_btn.isr(mraa.EDGE_RISING, capture_callback, capture_btn)

# Initialize Filter button
filter_btn = mraa.Gpio(29);
filter_btn.dir(mraa.DIR_IN)
filter_btn.isr(mraa.EDGE_RISING, filter_callback, filter_btn)

while 1:
    lock = _thread.allocate_lock()
    
    # Show live preview
    process_image("TAKE", 220, 180)

    if pressed==True:
        pressed = False
        _thread.start_new_thread(countdown, ("Countdown-Thread", lock,))

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Do cleanup
cap.release()
cv2.destroyAllWindows()
