import socket
import cv2
import pickle
import struct
import imutils
import threading
from time import sleep
import RPi.GPIO as GPIO

MOTION_SENSOR_PIN = 7
LED_PIN = 11

# is the server in the cloud?
IN_CLOUD = True

# server ip and port
HOST = "redacted" if IN_CLOUD else "127.0.0.1"
PORT = 25565

# create a socket connection to the server
client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.connect((HOST, PORT))

# start capturing video
vid = cv2.VideoCapture(0)

def setup_pins():
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(MOTION_SENSOR_PIN, GPIO.IN)
    GPIO.setup(LED_PIN, GPIO.OUT)

def motion_detect():
    #if client_socket:
        while vid.isOpened():
            # detect motion
            
            if GPIO.input(MOTION_SENSOR_PIN): ## if motion detected ##
                try:
                    # read the video stream
                    img, frame = vid.read()

                    # dump the frame into a sendable format
                    a = pickle.dumps(frame)
                    # pack the message including the message length
                    message = struct.pack("Q", len(a)) + a
                    # send the img data to the server
                    client_socket.sendall(message)
                    #cv2.imshow("test", frame)
                    # if user presses q key then close the socket and stop the program, required for cv2
                    key = cv2.waitKey(10)
                    if key == ord("q"): 
                        client_socket.close()

                    # small cooldown period, unlikely to have better results with full framerate
                    sleep(0.2)
                except:
                    # video has been stopped, stop trying to send data
                    print("Client stopped.")
                    break

def receive():
    # keep trying
    while True:
        # get message from server
        message = client_socket.recv(4)
        # if there's a message
        if message:
            # if the message is 1
            if b"1" in message:
                # turn the light on for 1 second
                GPIO.output(LED_PIN, GPIO.HIGH)
                sleep(1)
                GPIO.output(LED_PIN, GPIO.LOW)

setup_pins()

motion_thread = threading.Thread(target=motion_detect)
receive_thread = threading.Thread(target=receive)
motion_thread.start()
receive_thread.start()