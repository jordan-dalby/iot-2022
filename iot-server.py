import socket
import cv2
import pickle
import struct
import threading
from time import sleep
import mysql.connector
from datetime import datetime

# when in azure, this script will not need to display any results, so we can turn them off to save processing power
# we can also change the host IP address to the one that azure likes
IN_CLOUD = True

# server ip and port
HOST = "0.0.0.0" if IN_CLOUD else "127.0.0.1"
PORT = 25565

# create server socket to allow clients to connect
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# declare host and port pair
server_address = ((HOST, PORT))
# bind server socket to host and port
server_socket.bind(server_address)
# let the server start listening
server_socket.listen()

# declare face cascade to identify faces
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

# create a custom trained recognizer for identifying students faces
rec = cv2.face.LBPHFaceRecognizer_create()
rec.read("trained-dataset.yml")

# connect to sql database
db = mysql.connector.connect(
    db="jordandalby_iot",
    host="ysjcs.net",
    port=3306,
    user="redacted",
    password="redacted"
)

# declare the cursor used for querys
cursor = db.cursor()

# declare a dictionary of student_id:datetime
# where datetime is when their current lecture ends
# students get added to this dictionary when they first register for a module
# this should be routinely reset to preserve memory
# we keep track of this data locally so that we don't have to send requests to the SQL server as frequently
# just incase a student keeps leaving and returning to a module room
registered_students = {}

print(f"Waiting for clients to connect...")

#src: https://pyshine.com/Socket-Programming-with-multiple-clients/
def get_data(addr, client_socket):
    try:
        print(f"Client {addr} connected")
        # if the client_socket exists
        if client_socket:
            # declare some variables
            data = b""
            # find base size of payload
            payload_size = struct.calcsize("Q")
            while True:
                # loop until payload_size data is received, append all data to the 'data' variable
                while len(data) < payload_size:
                    packet = client_socket.recv(4 * 1024)
                    if not packet: break
                    data += packet
                # find the message size by slicing the data until it reaches the payload_size
                packed_msg_size = data[:payload_size]
                data = data[payload_size:]
                # find the full message size
                msg_size = struct.unpack("Q", packed_msg_size)[0]

                # loop until the data exceeds or matches the message size
                while len(data) < msg_size:
                    # get data from client socket
                    data += client_socket.recv(4 * 1024)
                # find frame data from packet based on the size of the message
                frame_data = data[:msg_size]
                data = data[msg_size:]
                # load the data previously dumped into an image
                frame = pickle.loads(frame_data)

                # identify any faces in the image
                identify_face(frame, client_socket)

                # if user presses q during this time, break
                key = cv2.waitKey(1)
                if key == ord("q"):
                    break
            # close client socket 
            client_socket.close()
    except Exception as e:
        print(f"Client {addr} disconnected")
        pass

# partial src: https://www.digitalocean.com/community/tutorials/how-to-detect-and-extract-faces-from-an-image-with-opencv-and-python
def identify_face(frame, client_socket):
    # convert image to grayscale
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    # detect faces in the image, do not identify yet
    faces = face_cascade.detectMultiScale(gray, 1.5, 5)

    # declare id of student as 0
    id=0
    # loop all identified faces, stored as ROI (region of interest)
    for (x, y, w, h) in faces:
        # create a rectangle around ROI
        if not IN_CLOUD:
            cv2.rectangle(frame, (x , y), (x + w, y + h), (255, 0, 0), 2)
        
        # try to identify ROI with loaded trained data, also calculate a confidence value
        id, conf = rec.predict(gray[y:y + h, x:x + w])

        # conf is inverse, <70 is high prediction
        # so if conf exceeds 100 it's definitely not a student in the trained data
        if conf > 100:
            id = 0
        
        if id != 0:
            # start a thread for updating the attendance, we don't want to interfere with potentially receiving
            # another frame while this runs
            update_thread = threading.Thread(target=send_attendance_update, args=[id])
            update_thread.start()
            send_success(client_socket)

        # write student id to image
        if not IN_CLOUD:
            cv2.putText(frame, str(id) + " " + str(conf), (x, y + h), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255))

    print(len(faces))
    
    # display image that shows all student faces in image
    if not IN_CLOUD:
        cv2.imshow('Receiving...', frame)

def send_success(client_socket):
    # send a 1 to the client, this indicates a successful identification
    client_socket.send(b"1")

def send_attendance_update(guess_student_id):
    # if student has registered
    if guess_student_id in registered_students:
        # get current time
        now = datetime.now()
        # if student is trying to reregister before the end of their current module, return
        if now < registered_students[guess_student_id]:
            # don't allow student to reregister before their timeout expires
            print(f"Student {guess_student_id} already registered")
            return

    # find all modules that this student is enrolled in
    cursor.execute(f"SELECT * FROM enrolment WHERE student_id={guess_student_id}")
    result = cursor.fetchall()
    
    # loop all enrolments
    for enrolment_data in result:
        # find a module id from the results
        cursor.reset()
        cursor.execute(f"SELECT * FROM modules WHERE module_id={enrolment_data[1]}")
        module_data = cursor.fetchone()
        # if a module is found
        if cursor.rowcount != 0:
            # module exists
            # find the most recent time table entry for this module
            # uses two select statements combined, firstly this line will find the most recent start_date for the fetched_module_id
            # and then execute a select on the most recent start_time that was found
            cursor.execute(f"SELECT * FROM timetable_entries WHERE module_id={module_data[0]} AND start_time=(SELECT MAX(start_time) FROM timetable_entries WHERE module_id={module_data[0]})")
            timetable_data = cursor.fetchone()

            # check if student is already registered for this module
            cursor.execute(f"SELECT * FROM attendance WHERE timetable_entry_id={timetable_data[0]} AND student_id={guess_student_id}")
            _ = cursor.fetchall()
            if cursor.rowcount != 0:
                # student already registered for this time tabled module
                print(f"Student {guess_student_id} already registered for {module_data[1]}.")
                # keep track of when the student should be allowed to register again
                registered_students[guess_student_id] = timetable_data[3]
                return
            # reset the cursor to clear any results
            cursor.reset()

            # outcome of this attendance update
            outcome = ""

            # find the date and time now
            now = datetime.now()
            # if now is before or equal to the start_time then the student is present and on-time
            if now <= timetable_data[2]:
                # student is on time
                print(f"Student {guess_student_id} registered. ({module_data[1]}) (Present)")
                outcome = "PRESENT"
            # if the student arrives during the module, they are late
            elif now > timetable_data[2] and now < timetable_data[3]:
                # student is late
                print(f"Student {guess_student_id} registered. ({module_data[1]}) (Late)")
                outcome = "LATE"
            # if the student arrives at any other time they have missed the module
            else:
                print(f"Student {guess_student_id} registered. ({module_data[1]}) (Missed module)")
                outcome = "MISSED"
            
            # keep track of when the student should be allowed to register again
            registered_students[guess_student_id] = timetable_data[3]

            # format the current datetime
            formatted_now = now.strftime('%Y-%m-%d %H:%M:%S')
            # insert the attendance of the student in the attendance table
            cursor.execute(f"INSERT INTO attendance (arrival_time, student_id, timetable_entry_id, present) VALUES (\"{formatted_now}\", {guess_student_id}, {timetable_data[0]}, \"{outcome}\")")
            # commit the changes
            db.commit()
            # return, don't want to do any more modules
            return
        else:
            print(f"Module {enrolment_data[1]} was not found")
            return

while True:
    # allow server to accept connections
    client_socket, addr = server_socket.accept()
    # declare thread for this client, constantly try to get new data
    thread = threading.Thread(target=get_data, args=(addr, client_socket))
    # start the thread
    thread.start()
