import subprocess
import sys
import os
import socket
import queue
import threading
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import csv
import time
import datetime
import numpy
from itertools import count

N_SENSORS=2
AREF_VOLTAGE=5.15
ADC_BITS=10
ADC_RESOLUTION=(2**ADC_BITS)-1

def retrieve_measurement_data(data_queue):
    connection_addr=("localhost", 25565)
    try:
        data_socket = socket.socket()
        data_socket.connect(connection_addr)
    except socket.timeout:
        print("ERROR: Could not connect")
    while True:
        # Data comes in this format: <|ABCD||ABCD||...|>
        # NUMBER 4 here should be replaced by a variable
        my_data = data_socket.recv(2+N_SENSORS*(2+4))
        decoded_data = my_data.decode("utf-8")
        data_string = decoded_data.replace("<|", "")
        data_string = data_string.replace("|>", "")
        serialized_data_list = data_string.split("||")
        data_list = [int (x) for x in serialized_data_list]
        try:
            data_queue.put(data_list, block=False)
        except queue.Full:
            print("Data queue is full")

def get_reading_value(data_queue, value_queues, csv_writer):
    # Wait, for synchronization purposes
    time.sleep(5)
    while True:
        try:
            data_list = data_queue.get(block=True, timeout=0.1)
            data_queue.task_done()
        except queue.Empty:
            data_list=[0]*N_SENSORS
        ts = time.time()
        sttime = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d_%H:%M:%S.%f')[:-3]
        readings = [sttime]
        readings.extend(data_list)
        csv_writer.writerow(readings)
        print(readings)
        try:
            for index, value in enumerate(data_list):
                value_queues[index].put(value, block=False)
        except queue.Full:
            print("WARNING: Value queue is full, dumping new readings")

def retrieve_value_from_data_list(frames, value_queues, x_vals, y_vals, time_stamp, index, axes):
    x_vals[index][0].append(next(time_stamp[index]))
    x_vals[index][1].append(next(time_stamp[index]))
    try:
        value = value_queues[index].get(block=True, timeout=0.1)
        value_queues[index].task_done()
    except queue.Empty:
        value=0
    # Voltage
    voltage_value = float( (value*AREF_VOLTAGE) / ADC_RESOLUTION)
    y_vals[index][0].append(voltage_value)
    # Resistance
    resistance_value = float( (2*value*AREF_VOLTAGE) / ADC_RESOLUTION)
    y_vals[index][1].append(resistance_value)
    # Fix so we show both voltage and resistance
    if type(axes) == numpy.ndarray:
        axes[0][index].cla()
        axes[0][index].plot(x_vals[index][0], y_vals[index][0])
        axes[1][index].cla()
        axes[1][index].plot(x_vals[index][1], y_vals[index][1])
    else:
        axes[0].cla()
        axes[0].plot(x_vals[index][0], y_vals[index][0])
        axes[1].cla()
        axes[1].plot(x_vals[index][1], y_vals[index][1])


def make_animation(data_queue, csv_file):
    value_queues = {}
    x_vals={}
    y_vals={}
    for sensor in range(N_SENSORS):
        # Tuple will work for (Voltage, Resistance)
        x_vals[sensor]=([], [])
        y_vals[sensor]=([], [])
        # Maybe this is not needed, I used a single queue before and it worked, look closer at this later
        value_queues[sensor]=queue.Queue(100*N_SENSORS)
    if not os.path.exists("logs"):
        os.makedirs("logs")
    writer=csv.writer(csv_file)
    description_list=["sensor"+str(x) for x in range(N_SENSORS)]
    description_list.insert(0, "time")
    writer.writerow(description_list)
    try:
        data_ordering_thread = threading.Thread(target=get_reading_value, name="data_ordering_thread", args=(data_queue, value_queues, writer))
    except:
        print("[ANIMATION] ERROR: Could not create thread")
    data_ordering_thread.start()

    index = count()
    time_stamps=[index]*N_SENSORS

    fig, axes = plt.subplots(nrows=2, ncols=N_SENSORS)
    anims=[]
    for sensor in range(N_SENSORS):
        anim=animation.FuncAnimation(fig, retrieve_value_from_data_list, fargs=(value_queues, x_vals, y_vals, time_stamps, sensor, axes), interval=100/N_SENSORS)
        anims.append(anim)
    plt.tight_layout()
    plt.show()
    for sensor in range(N_SENSORS):
        value_queues[sensor].join()

python_interp=sys.executable
inter_path=os.path.dirname(os.path.realpath(__file__))
try:
    serial_read_subproc = subprocess.Popen([python_interp, os.path.join(inter_path,"osc.py")])
except subprocess.CalledProcessError as err:
    print("ERROR: " + err.stderr.decode("utf-8"))
    exit(1)
# This means we may a maximum of 5 minutes of measurement buffering in the queue
# Measurements arrive every 0.1s
# This queue will be accessed 
#   1) When a measurement arrives from the socket
#   2) When the animation function is called to retrieve a frame
data_queue = queue.Queue(3000)

try:
    retriever_thread = threading.Thread(target=retrieve_measurement_data, name="retriever_thread", args=(data_queue, ))
except Exception as e:
    print("[MAIN] ERROR: Could not create thread")
    e.with_traceback()
retriever_thread.start()
ts = time.time()
sttime = datetime.datetime.fromtimestamp(ts).strftime('%Y-%M-%d_%H-%M-%S')
file_name="log_"+sttime+".csv"
csv_file = open (os.path.join("logs", file_name), "w", newline="")
make_animation(data_queue, csv_file)
csv_file.close()
data_queue.join()
#print(my_osc.sample_buffer)
#exit(0)
