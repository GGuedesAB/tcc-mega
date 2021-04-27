import subprocess
import sys
import os
import socket
import queue
import threading
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import csv
import time
import datetime
import numpy
import argparse
from itertools import count
inter_path=os.path.dirname(os.path.realpath(__file__))
sys.path.append(inter_path)
from logger import Logger

R1=1
R2=4.4
V_A=1

parser = argparse.ArgumentParser(description='Interprets and plots results given by the Arduino.')
parser.add_argument('--nsensors', help='Number of sensors that will be monitored', type=int, required=True)
parser.add_argument('--port', help='Serial port name to connect', type=str, required=True)
parser.add_argument('--aref', help='Voltage reference of the Arduino board', type=float, default=5)
parser.add_argument('--adc_resolution', help='Number of bits of resolution of the ADC', type=int, default=10)
parser.add_argument('--verbose', help='Outputs all messages', action='store_true')
parser.add_argument('--virtual', help="Create virtual serial connection", action='store_true')
args = parser.parse_args()

def retrieve_measurement_data(data_queue, nsensors, stop):
    retriever_logger=Logger("SOCKET-RECV")
    if args.verbose:
        retriever_logger.set_debug()
    else:
        retriever_logger.set_error()
    connection_addr=('localhost', 25565)
    try:
        data_socket = socket.socket()
        data_socket.connect(connection_addr)
    except socket.timeout:
        retriever_logger.error("Could not connect")
    while not stop[0]:
        # Data comes in this format: <|ABCD||ABCD||...|>
        # NUMBER 4 here should be replaced by a variable
        try:
            my_data = data_socket.recv(2+nsensors*(2+4))
            decoded_data = my_data.decode("utf-8")
            data_string = decoded_data.replace("<|", "")
            data_string = data_string.replace("|>", "")
            serialized_data_list = data_string.split("||")
            try:
                data_list = [int (x) for x in serialized_data_list]
                data_queue.put(data_list, block=False)
            except queue.Full:
                retriever_logger.warning("Data queue is full, dumping new measurements")
            except ValueError:
                pass
        except ConnectionResetError:
            pass

def make_animation(data_queue, csv_file, nsensors, aref_voltage, adc_resoltuion):
    animation_logger=Logger("ANIMATION")
    if args.verbose:
        animation_logger.set_debug()
    else:
        animation_logger.set_error()
    x_vals={}
    y_vals={}
    for sensor in range(nsensors):
        # Tuple will work for (Voltage, Resistance)
        x_vals[sensor]=([], [])
        y_vals[sensor]=([], [])
    if not os.path.exists("logs"):
        os.makedirs("logs")
    writer=csv.writer(csv_file)
    description_list=["sensor"+str(x) for x in range(nsensors)]
    description_list.insert(0, "time")
    writer.writerow(description_list)

    index = count()
    next(index)
    fig, axes = plt.subplots(nrows=2, ncols=nsensors)
    axes[0][0].set_ylabel("Voltage in sensors")
    axes[1][0].set_ylabel("Resistance of sensors")
    lines=[]
    for row in range(2):
        for column in range(nsensors):
            lines.append(axes[row][column].plot([],[])[0])
            if (row == 0):
                axes[row][column].set_ylim(-0.1, 1.9)
            else:
                # TODO: Find out limit of resistance
                axes[row][column].set_ylim(-0.1, 6)
            axes[row][column].set_xlim(auto=True)

    def animate(i):
        try:
            # Animation is called every 50ms, wait, at max, more 50ms here
            data_list = data_queue.get(block=True, timeout=0.05)
            data_queue.task_done()
        except queue.Empty:
            data_list=[0]*nsensors
        ts = time.time()
        sttime = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d_%H:%M:%S.%f')[:-3]
        readings = [sttime]
        readings.extend(data_list)
        writer.writerow(readings)
        sample=next(index)
        row = 0
        for j, line in enumerate(lines):
            sensor_id=j%nsensors
            if j > 0 and j % nsensors == 0:
                row+=1
            # Voltage
            if row == 0:
                x_vals[sensor_id][row].append(sample)
                voltage_read=float((aref_voltage*data_list[sensor_id])/adc_resoltuion)
                voltage_plot=(voltage_read+(R2/R1)*V_A)*(R1/(R1+R2))
                y_vals[sensor_id][row].append(voltage_plot)
            # Resistance
            else:
                x_vals[sensor_id][row].append(sample)
                # Change here
                resistance=float((aref_voltage*data_list[sensor_id])/adc_resoltuion)
                y_vals[sensor_id][row].append(resistance)
            axes[row][sensor_id].set_xlim(0, sample)
            line.set_data(x_vals[sensor_id][row], y_vals[sensor_id][row])
        return lines

    anim=animation.FuncAnimation(fig, animate, blit=True, cache_frame_data=False, interval=10)
    plt.show()

if __name__ == "__main__":
    nsensors=args.nsensors
    aref_voltage=args.aref
    adc_bits=args.adc_resolution
    adc_resoltuion=(2**adc_bits)-1
    gui_monitor_logger=Logger("MONITOR")
    if args.verbose:
        gui_monitor_logger.set_debug()
    else:
        gui_monitor_logger.set_error()
    port=args.port
    python_interp=sys.executable
    inter_path=os.path.dirname(os.path.realpath(__file__))
    if args.virtual:
        serial_monitor_cmd=[python_interp, os.path.join(inter_path,"virtual_sensor.py"), "--port", "dummy", "--nsensors", str(nsensors)]
    else:
        serial_monitor_cmd=[python_interp, os.path.join(inter_path,"osc.py"), "--port", port, "--nsensors", str(nsensors)]
    if args.verbose:
        serial_monitor_cmd.append("--verbose")
    stop_threads=[False]
    try:
        try:
            serial_read_subproc = subprocess.Popen(serial_monitor_cmd)
        except subprocess.CalledProcessError as err:
            gui_monitor_logger.error(err.stderr.decode("utf-8"))
            exit(1)
        time.sleep(5)
        poll = serial_read_subproc.poll()
        if poll is not None:
            exit(1)
        # This means we may a maximum of 5 minutes of measurement buffering in the queue
        # Measurements arrive every 0.1s
        # This queue will be accessed 
        #   1) When a measurement arrives from the socket
        #   2) When the animation function is called to retrieve a frame
        data_queue = queue.Queue(3000)
        try:
            retriever_thread = threading.Thread(target=retrieve_measurement_data, name="retriever_thread", args=(data_queue, nsensors, stop_threads))
        except Exception as e:
            gui_monitor_logger.error("Could not create thread")
            e.with_traceback()
        retriever_thread.start()
        ts = time.time()
        sttime = datetime.datetime.fromtimestamp(ts).strftime('%Y-%M-%d_%H-%M-%S')
        file_name="log_"+sttime+".csv"
        if not os.path.exists(os.path.join(inter_path, "logs")):
            os.makedirs(os.path.join(inter_path, "logs"))
        csv_file = open (os.path.join(inter_path, "logs", file_name), "w", newline="")
        make_animation(data_queue, csv_file, nsensors, aref_voltage, adc_resoltuion)
        csv_file.close()
        stop_threads[0]=True
        serial_read_subproc.kill()
    except KeyboardInterrupt:
        gui_monitor_logger.warning("Please, close the running figure")
        stop_threads[0]=True
        serial_read_subproc.kill()
    exit(0)
