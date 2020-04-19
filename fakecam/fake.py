import os
import cv2
import numpy as np
import requests
import pyfakewebcam
from signal import signal, SIGINT
from sys import exit

# setup access to the *real* webcam
cap = cv2.VideoCapture('/dev/video0')
height, width = 720, 1280
cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
cap.set(cv2.CAP_PROP_FPS, 30)

# The scale factor for image sent to bodypix
sf = 0.5

# setup the fake camera
fake = pyfakewebcam.FakeWebcam('/dev/video2', width, height)


def handler(signal_received, frame):
    # load the virtual background
    global background
    background = cv2.imread("background.jpg")
    background = cv2.resize(background, (width, height))
    print('Reloaded the background image')

    global foreground
    foreground = cv2.imread("foreground.jpg", cv2.IMREAD_GRAYSCALE)
    if foreground is None:
        foreground = np.zeros((height,width), np.float)
        print('Using empty foreground mask')
    else:
        foreground = cv2.resize(foreground.astype(float), (width, height)) / 255.0
        print('Reloaded the foreground mask')

    global inv_foreground
    inv_foreground = 1 - foreground

def get_mask(frame, bodypix_url='http://127.0.0.1:9000'):
    frame = cv2.resize(frame, (0, 0), fx=sf, fy=sf)
    _, data = cv2.imencode(".png", frame)
    r = requests.post(
        url=bodypix_url,
        data=data.tobytes(),
        headers={'Content-Type': 'application/octet-stream'})
    mask = np.frombuffer(r.content, dtype=np.uint8)
    mask = mask.reshape((frame.shape[0], frame.shape[1]))
    mask = cv2.resize(mask, (0, 0), fx=1/sf, fy=1/sf,
                      interpolation=cv2.INTER_NEAREST)
    mask = cv2.dilate(mask, np.ones((20,20), np.uint8) , iterations=1)
    mask = cv2.blur(mask.astype(float), (30,30))
    return mask

def shift_image(img, dx, dy):
    img = np.roll(img, dy, axis=0)
    img = np.roll(img, dx, axis=1)
    if dy>0:
        img[:dy, :] = 0
    elif dy<0:
        img[dy:, :] = 0
    if dx>0:
        img[:, :dx] = 0
    elif dx<0:
        img[:, dx:] = 0
    return img

def get_frame(cap, background, foreground, inv_foreground):
    _, frame = cap.read()
    # fetch the mask with retries (the app needs to warmup and we're lazy)
    # e v e n t u a l l y c o n s i s t e n t
    mask = None
    while mask is None:
        try:
            mask = get_mask(frame)
        except:
            print("mask request failed, retrying")
    # composite the foreground and background
    inv_mask = 1-mask
    for c in range(frame.shape[2]):
        frame[:,:,c] = (frame[:,:,c]*mask + background[:,:,c]*inv_mask)*inv_foreground + background[:,:,c]*foreground
    return frame

if __name__ == '__main__':
    signal(SIGINT, handler)
    handler(None, None)

    print('Running...')
    print('Please press CTRL-\ to exit.')
    print('Please CTRL-C to reload the background image')
    # frames forever
    while True:
        frame = get_frame(cap, background, foreground, inv_foreground)
        # fake webcam expects RGB
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        fake.schedule_frame(frame)
