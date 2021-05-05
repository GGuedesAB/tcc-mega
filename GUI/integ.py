import subprocess
import sys
import os
import socket
import queue
import threading
from matplotlib.artist import Artist
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import csv
import time
import datetime
import argparse
import signal
import numpy
from itertools import count, cycle
inter_path=os.path.dirname(os.path.realpath(__file__))
sys.path.append(inter_path)
from logger import Logger

R1=1
R2=4.4
V_A=1
SAMPLING_PERIOD=1
# 32 sensors in chip matrix + VREF_A + VREF_B
MAX_SENSORS=34
R_OF_IREF=200E3

parser = argparse.ArgumentParser(description='Interprets and plots results given by the Arduino.')
#parser.add_argument('--nsensors', help='Number of sensors that will be monitored', type=int, required=True)
parser.add_argument('--port', help='Serial port name to connect', type=str, required=True)
parser.add_argument('--aref', help='Voltage reference of the Arduino board', type=float, default=5)
parser.add_argument('--adc_resolution', help='Number of bits of resolution of the ADC', type=int, default=10)
parser.add_argument('--verbose', help='Outputs all messages', action='store_true')
parser.add_argument('--virtual', help="Create virtual serial connection", action='store_true')
#parser.add_argument('--no-gui', help="Do not show GUI", action='store_true')
args = parser.parse_args()

def int_to_voltage(int_value, aref_voltage, adc_resoltuion):
    return float((aref_voltage*int_value)/adc_resoltuion)

def retrieve_measurement_data(data_queue, aref_voltage, adc_resoltuion, stop, data_socket, vref, iref):
    retriever_logger=Logger("SOCKET-RECV")
    if args.verbose:
        retriever_logger.set_debug()
    else:
        retriever_logger.set_error()
    vref_A_new=0
    vref_A_old=0
    vref_B_new=0
    vref_B_old=0
    while not stop[0]:
        # Data comes in this format: <|ABCD||ABCD||...|>
        # NUMBER 4 here should be replaced by a variable
        try:
            my_data = data_socket.recv(2+MAX_SENSORS*(2+4))
            decoded_data = my_data.decode("utf-8")
            data_string = decoded_data.replace("<|", "")
            data_string = data_string.replace("|>", "")
            serialized_data_list = data_string.split("||")
            vref_A_old=vref_A_new
            vref_A_new=int(serialized_data_list[0])
            vref_B_old=vref_B_new
            vref_B_new=int(serialized_data_list[1])
            # Calculate IREF
            vout_ref_A_1=int(serialized_data_list[2])
            vout_ref_A_2=int(serialized_data_list[5])
            vout_ref_A_med=int((vout_ref_A_1+vout_ref_A_2)/2)
            iref_A=int_to_voltage(vout_ref_A_med-vref_A_new, aref_voltage, adc_resoltuion)/R_OF_IREF
            calculated_vref_A=int_to_voltage(vref_A_new, aref_voltage, adc_resoltuion)

            vout_ref_B_1=int(serialized_data_list[18])
            vout_ref_B_2=int(serialized_data_list[21])
            vout_ref_B_med=int((vout_ref_B_1+vout_ref_B_2)/2)
            iref_B=int_to_voltage(vout_ref_B_med-vref_B_new, aref_voltage, adc_resoltuion)/R_OF_IREF
            calculated_vref_B=int_to_voltage(vref_B_new, aref_voltage, adc_resoltuion)

            # Output parameters
            vref[0]=calculated_vref_A
            vref[1]=calculated_vref_B
            iref[0]=iref_A
            iref[1]=iref_B

            if vref_A_old == 0 and vref_A_old != vref_A_new:
                print(f"[VREF] INFO: VREF_A = {calculated_vref_A:.3f} V")
                print(f"             IREF_A = {iref_A*10E9:.0f} nA")
            if (vref_A_old != 0 and vref_A_old != vref_A_new) or (vref_B_old != 0 and vref_B_old != vref_B_new):
                print(f"[VREF] WARNING: Fluctuation in VREF.")
                print(f"                Current VREF_A = {calculated_vref_A:.3f} V")
                print(f"                Current IREF_A = {iref_A*10E9:.0f} nA")
                print(f"                Current VREF_B = {calculated_vref_B:.3f} V")
                print(f"                Current IREF_B = {iref_B*10E9:.0f} nA")
            if vref_B_old == 0 and vref_B_old != vref_B_new:
                print(f"[VREF] INFO: VREF_B = {calculated_vref_B:.3f} V")
                print(f"             IREF_B = {iref_B*10E9:.0f} nA")
            try:
                data_list = [int (x) for x in serialized_data_list]
                data_queue.put(data_list, block=False)
            except queue.Full:
                retriever_logger.warning("Data queue is full, dumping new measurements")
            except ValueError:
                pass
        except ConnectionResetError:
            pass
        except ConnectionAbortedError:
            retriever_logger.warning("Server has closed the connection")
        except Exception as e:
            e.with_traceback()
            exit(1)
    retriever_logger.debug("Bye")

def make_animation(data_queue, csv_file, nsensors, aref_voltage, adc_resoltuion, vref, iref, stop_threads):
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
    # VREF_A is taken as sensor0, V_REFB is taken as sensor1
    description_list=["sensor"+str(x) for x in range(MAX_SENSORS)]
    description_list.insert(0, "time")
    writer.writerow(description_list)

    index = count()
    next(index)
    fig, axes = plt.subplots(nrows=2, ncols=nsensors)
    axes[0][0].set_ylabel("Voltage in sensors (V)")
    axes[0][0].set_title('Reference resistor A')
    axes[0][1].set_title('Deposited resistor A')
    axes[0][2].set_title('Reference resistor B')
    axes[0][3].set_title('Deposited resistor B')
    axes[1][0].set_ylabel("Resistance of sensors (kOhms)")
    lines=[]
    smaller_measured_resistance=[50, 50, 50, 50]
    biggest_measured_resistance=[100, 100, 100, 100]
    for row in range(2):
        for column in range(nsensors):
            lines.append(axes[row][column].plot([],[])[0])
            axes[row][column].grid(which='major', alpha=0.5)
            axes[row][column].grid(which='minor', alpha=0.2)
            if (row == 0):
                major_ticks=numpy.arange(0,2.1,0.3)
                minor_ticks=numpy.arange(0,2.1,0.15)
                axes[row][column].set_yticks(major_ticks)
                axes[row][column].set_yticks(minor_ticks, minor=True)
                axes[row][column].set_ylim(-0.1, 2.0)
                axes[row][column].axhline(y=0.9, color='r', linestyle=':')
                axes[row][column].axhline(y=1.8, color='r', linestyle=':')
            else:
                axes[row][column].set_ylim(-0.1, 200)
    texts=[]

    def animate(i):
        try:
            data_list = data_queue.get(block=True, timeout=SAMPLING_PERIOD)
            data_queue.task_done()
        except queue.Empty:
            animation_logger.warning("Did not recieve measurement data from socket. Replacing with 0's")
            data_list=[0]*MAX_SENSORS
        ts = time.time()
        sttime = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d_%H:%M:%S.%f')[:-3]
        readings = [sttime]
        readings.extend(data_list)
        # VREF_A is taken as sensor0
        # VREF_B is taken as sensor1
        writer.writerow(readings)
        sample=next(index)
        # Do not show VREFs
        visible_data_list=data_list[2:]
        row = 0
        # These are
        #   First reference in A
        #   First deposited in A
        #   First reference in B
        #   First deposited in B
        sensors=cycle([0,1,16,17])
        for text in texts:
            text.set_visible(False)
        for j, line in enumerate(lines):
            real_sensor_id=next(sensors)
            sensor_id=j%nsensors
            if j > 0 and j % nsensors == 0:
                row+=1
            # Voltage
            if row == 0:
                x_vals[sensor_id][row].append(sample)
                voltage_read=float((aref_voltage*visible_data_list[real_sensor_id])/adc_resoltuion)
                voltage_plot=(voltage_read+(R2/R1)*V_A)*(R1/(R1+R2))
                text = f"{voltage_plot:.3f}"
                y_vals[sensor_id][row].append(voltage_plot)
                texts.append(axes[0][sensor_id].text(1, 1.05, text, fontweight='bold', fontsize='medium', horizontalalignment='right', verticalalignment='top', transform=axes[0][sensor_id].transAxes))
            # Resistance
            else:
                x_vals[sensor_id][row].append(sample)
                voltage_read=float((aref_voltage*visible_data_list[real_sensor_id])/adc_resoltuion)
                voltage_plot=(voltage_read+(R2/R1)*V_A)*(R1/(R1+R2))
                try:
                    if real_sensor_id < 2:
                        # Group A
                        resistance=(voltage_plot-vref[0])/iref[0]
                    else:
                        # Group B
                        resistance=(voltage_plot-vref[1])/iref[1]
                except ZeroDivisionError:
                    resistance=0
                # Show in kOhms
                resistance = resistance/10E3
                if resistance < 0:
                    animation_logger.debug("Negative resistance!")
                text = f"{resistance:.3f}"
                texts.append(axes[1][sensor_id].text(1, 1.05, text, fontweight='bold', fontsize='medium', horizontalalignment='right', verticalalignment='top', transform=axes[1][sensor_id].transAxes))
                if smaller_measured_resistance[sensor_id] <= 50 or (resistance > 50 and resistance < smaller_measured_resistance[sensor_id]):
                    smaller_measured_resistance[sensor_id] = resistance - 50
                if resistance > biggest_measured_resistance[sensor_id]:
                    biggest_measured_resistance[sensor_id] = resistance + 50
                y_vals[sensor_id][row].append(resistance)
            axes[row][sensor_id].set_xlim(0, sample)
            axes[1][sensor_id].set_ylim(smaller_measured_resistance[sensor_id], biggest_measured_resistance[sensor_id])
            line.set_data(x_vals[sensor_id][row], y_vals[sensor_id][row])
        return lines

    anim=animation.FuncAnimation(fig, animate, blit=False, cache_frame_data=False, interval=800)
    plt.show()

if __name__ == "__main__":
    gui_monitor_logger=Logger("MONITOR")
    if args.verbose:
        gui_monitor_logger.set_debug()
    else:
        gui_monitor_logger.set_error()
    #nsensors=args.nsensors
    nsensors=4
    if nsensors > MAX_SENSORS:
        gui_monitor_logger.error(f"Only {MAX_SENSORS} sensors can be viewed. {nsensors} passed.")
        exit(1)
    aref_voltage=args.aref
    adc_bits=args.adc_resolution
    adc_resoltuion=(2**adc_bits)-1
    port=args.port
    python_interp=sys.executable
    inter_path=os.path.dirname(os.path.realpath(__file__))
    if args.virtual:
        gui_monitor_logger.error("Virtual sensor is not supported yet")
        exit(1)
        serial_monitor_cmd=[python_interp, os.path.join(inter_path,"virtual_sensor.py"), "--port", "dummy", "--nsensors", str(MAX_SENSORS)]
    else:
        serial_monitor_cmd=[python_interp, os.path.join(inter_path,"osc.py"), "--port", port, "--nsensors", str(MAX_SENSORS)]
    server_addr=('localhost', 25565)
    serial_server = socket.socket()
    serial_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serial_server.bind(server_addr)
    if args.verbose:
        serial_monitor_cmd.append("--verbose")
    stop_threads=[False]
    try:
        try:
            serial_read_subproc = subprocess.Popen(serial_monitor_cmd)
        except subprocess.CalledProcessError as err:
            gui_monitor_logger.error(err.stderr.decode("utf-8"))
            exit(1)
        time.sleep(1)
        poll = serial_read_subproc.poll()
        if poll is not None:
            exit(1)
        try:
            serial_server.settimeout(5)
            serial_server.listen(1)
            conn, addr = serial_server.accept()
            gui_monitor_logger.info(f"Connected to {addr}")
        except socket.timeout:
            if sys.platform == "win32":
                serial_read_subproc.kill()
            else:
                serial_read_subproc.send_signal(signal.SIGINT)
            poll = serial_read_subproc.poll()
            while poll is None:
                gui_monitor_logger.debug("Waiting subprocess")
                time.sleep(1)
                poll = serial_read_subproc.poll()
            exit(1)

        # This means we may a maximum of 5 minutes of measurement buffering in the queue
        # Measurements arrive every 0.1s
        # This queue will be accessed 
        #   1) When a measurement arrives from the socket
        #   2) When the animation function is called to retrieve a frame
        data_queue = queue.Queue(3000)
        vref=[0, 0]
        iref=[0, 0]
        try:
            retriever_thread = threading.Thread(target=retrieve_measurement_data, name="retriever_thread", args=(data_queue, aref_voltage, adc_resoltuion, stop_threads, conn, vref, iref))
        except Exception as e:
            gui_monitor_logger.error("Could not create thread")
            e.with_traceback()
        retriever_thread.start()

        ts = time.time()
        sttime = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d_%H-%M-%S')
        file_name="log_"+sttime+".csv"
        if not os.path.exists(os.path.join(inter_path, "logs")):
            os.makedirs(os.path.join(inter_path, "logs"))
        csv_file = open (os.path.join(inter_path, "logs", file_name), "w", newline="")

        make_animation(data_queue, csv_file, nsensors, aref_voltage, adc_resoltuion, vref, iref, stop_threads)

        stop_threads[0]=True
        retriever_thread.join()
        if sys.platform == "win32":
            serial_read_subproc.kill()
        else:
            serial_read_subproc.send_signal(signal.SIGINT)
        poll = serial_read_subproc.poll()
        while poll is None:
            time.sleep(1)
            gui_monitor_logger.debug("Waiting subprocess")
            poll = serial_read_subproc.poll()
        csv_file.close()
        conn.close()
        serial_server.close()
        gui_monitor_logger.debug("Bye")
    except Exception as e:
        e.with_traceback()
    exit(0)
