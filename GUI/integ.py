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
PRECISION=2

def retrieve_measurement_data(data_queue):
    connection_addr=("localhost", 25565)
    try:
        data_socket = socket.socket()
        data_socket.connect(connection_addr)
    except socket.timeout:
        print("ERROR: Could not connect")
    while True:
        # Data comes in this format: <|value1||value2||...|>
        my_data = data_socket.recv(2+N_SENSORS*(2+2+PRECISION))
        decoded_data = my_data.decode("utf-8")
        data_string = decoded_data.replace("<|", "")
        data_string = data_string.replace("|>", "")
        serialized_data_list = data_string.split("||")
        data_list = [float (x) for x in serialized_data_list]
        try:
            data_queue.put(data_list, block=False)
        except queue.Full:
            print("Data queue is full")

def get_reading_value(data_queue, value_queue, csv_writer):
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
        try:
            value_queue.put(data_list, block=False)
        except queue.Full:
            print("WARNING: Value queue is full, dumping new readings")

def retrieve_value_from_data_list(frames, value_queue, x_vals, y_vals, time_stamp, index, axes):
    x_vals[index].append(next(time_stamp[index]))
    try:
        value_list = value_queue.get(block=True, timeout=0.1)
        value_queue.task_done()
    except queue.Empty:
        value=[0]*N_SENSORS
    y_vals[index].append(value_list[index])
    if type(axes) == numpy.ndarray:
        axes[index].cla()
        axes[index].plot(x_vals[index], y_vals[index])
    else:
        axes.cla()
        axes.plot(x_vals[index], y_vals[index])


def make_animation(data_queue, csv_file):
    value_queue = queue.Queue(100*N_SENSORS)
    if not os.path.exists("logs"):
        os.makedirs("logs")
    writer=csv.writer(csv_file)
    description_list=["sensor"+str(x) for x in range(N_SENSORS)]
    description_list.insert(0, "time")
    writer.writerow(description_list)
    try:
        data_ordering_thread = threading.Thread(target=get_reading_value, name="data_ordering_thread", args=(data_queue, value_queue, writer))
    except Exception as e:
        print("[ANIMATION] ERROR: Could not create thread")
    data_ordering_thread.start()

    x_vals=[[]]*N_SENSORS
    y_vals=[[]]*N_SENSORS
    index = count()
    time_stamps=[index]*N_SENSORS

    fig, axes = plt.subplots(nrows=2, ncols=N_SENSORS)
    voltage_anims=[]
    resistance_anims=[]
    for sensor in range(N_SENSORS):
        voltage_ani=animation.FuncAnimation(fig, retrieve_value_from_data_list, fargs=(value_queue, x_vals, y_vals, time_stamps, sensor, axes[0]), interval=10)
        #resistance_ani=animation.FuncAnimation(fig, retrieve_value_from_data_list, fargs=(value_queues, x_vals, y_vals, time_stamps, sensor, axes[1]), interval=1)
        voltage_anims.append(voltage_ani)
        #resistance_anims.append(resistance_ani)

    plt.tight_layout()
    plt.show()
    value_queue.join()

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
