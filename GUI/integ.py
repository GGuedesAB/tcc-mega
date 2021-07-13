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

from numpy.core.shape_base import block
inter_path=os.path.dirname(os.path.realpath(__file__))
sys.path.append(inter_path)
from logger import Logger

R1=1
R2=4.4
V_A=1
SAMPLING_PERIOD=61.2
DELTA=0.1*SAMPLING_PERIOD
SAMPLING_PERIOD=SAMPLING_PERIOD+DELTA
CAUTION_VOLTAGE=1.5
SATURATION_VOLTAGE=1.7
# 32 sensors in chip matrix + VREF_A + VREF_B
MAX_SENSORS=34
N_ROWS=2
N_COLS=3
SENSORS_PER_WINDOW=5
R_OF_IREF=200E3

parser = argparse.ArgumentParser(description='Interprets and plots results given by the Arduino.')
#parser.add_argument('--nsensors', help='Number of sensors that will be monitored', type=int, required=True)
parser.add_argument('--port', help='Serial port name to connect', type=str, required=True)
parser.add_argument('--aref', help='Voltage reference of the Arduino board', type=float, default=5)
parser.add_argument('--adc_resolution', help='Number of bits of resolution of the ADC', type=int, default=10)
parser.add_argument('--max-deviation', help='Max modular difference between a group of resistances (in kOhms)', type=int, default=10)
parser.add_argument('--verbose', help='Outputs all messages', action='store_true')
parser.add_argument('--virtual', help='Create virtual serial connection', action='store_true')
parser.add_argument('--calculate-values', help='Makes the calculations to find sensor resistance instead of using static formula', action='store_true')
#parser.add_argument('--no-gui', help="Do not show GUI", action='store_true')
args = parser.parse_args()
# Will not complain of high deviance unless resistance difference of a group is less than 10kOhms
ACCEPTABLE_DEVIANCE=args.max_deviation

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
            vout_ref_A_med=int_to_voltage(int((vout_ref_A_1+vout_ref_A_2)/2), aref_voltage, adc_resoltuion)
            vout_ref_A_med=(vout_ref_A_med + (V_A*R2)/R1)*(R1/(R1+R2))
            calculated_vref_A=int_to_voltage(vref_A_new, aref_voltage, adc_resoltuion)
            iref_A=(vout_ref_A_med - calculated_vref_A)/R_OF_IREF

            vout_ref_B_1=int(serialized_data_list[18])
            vout_ref_B_2=int(serialized_data_list[21])
            vout_ref_B_med=int_to_voltage(int((vout_ref_B_1+vout_ref_B_2)/2), aref_voltage, adc_resoltuion)
            vout_ref_B_med=(vout_ref_B_med + (V_A*R2)/R1)*(R1/(R1+R2))
            calculated_vref_B=int_to_voltage(vref_B_new, aref_voltage, adc_resoltuion)
            iref_B=(vout_ref_B_med - calculated_vref_B)/R_OF_IREF

            # Output parameters
            vref[0]=calculated_vref_A
            vref[1]=calculated_vref_B
            iref[0]=iref_A
            iref[1]=iref_B

            if vref_A_old == 0 and vref_A_old != vref_A_new:
                print(f"[VREF] INFO: VREF_A = {calculated_vref_A:.3f} V")
                print(f"             IREF_A = {iref_A*1E9:.0f} nA")
            if (vref_A_old != 0 and vref_A_old != vref_A_new) or (vref_B_old != 0 and vref_B_old != vref_B_new):
                print(f"[VREF] WARNING: Fluctuation in VREF.")
                print(f"                Current VREF_A = {calculated_vref_A:.3f} V")
                print(f"                Current IREF_A = {iref_A*1E9:.0f} nA")
                print(f"                Current VREF_B = {calculated_vref_B:.3f} V")
                print(f"                Current IREF_B = {iref_B*1E9:.0f} nA")
            if vref_B_old == 0 and vref_B_old != vref_B_new:
                print(f"[VREF] INFO: VREF_B = {calculated_vref_B:.3f} V")
                print(f"             IREF_B = {iref_B*1E9:.0f} nA")
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

def build_matrix_figure (list_of_titles):
    fig, axes = plt.subplots(nrows=N_ROWS, ncols=N_COLS)
    axes[0][0].set_ylabel("Resistance of sensors (kOhms)")
    axes[1][0].set_ylabel("Resistance of sensors (kOhms)")
    axes[0][0].set_title(list_of_titles[0])
    axes[0][1].set_title(list_of_titles[1])
    axes[1][0].set_title(list_of_titles[2])
    axes[1][1].set_title(list_of_titles[3])
    axes[1][2].set_title(list_of_titles[4])
    lines=[]
    for row in range(N_ROWS):
        for column in range(N_COLS):
            if row == 0 and column == 2:
                continue
            lines.append(axes[row][column].plot([],[])[0])
            axes[row][column].grid(which='major', alpha=0.5)
            axes[row][column].grid(which='minor', alpha=0.2)
            axes[row][column].set_ylim(-0.1, 200)
    return fig, axes, lines

def check_deviation(indexes, values, average, acceptable_dev, logger):
    for i, v in zip(indexes, values):
        dev = numpy.abs(v-average)
        if dev > acceptable_dev:
            # i+2 is to be coherent with resistance layout naming
            logger.warning(f"Sensor {i+2} has high deviation -> {(dev):.1f} kOhms")

def get_max_voltage(voltages, indexes):
    index = indexes[0]
    max_voltage = voltages[0]
    for i, voltage in enumerate(voltages):
        new_voltage = voltage
        if new_voltage > max_voltage:
            index = indexes[i]
            max_voltage = new_voltage
    return (index, max_voltage)

def get_voltages_resistances_and_average (matrix_indexes, float_data):

    matrix_voltages = [float_data[i][0] for i in matrix_indexes]
    matrix_resistances = [float_data[i][1] for i in matrix_indexes]
    max_voltage_tuple = get_max_voltage(matrix_voltages, matrix_indexes)
    matrix_average = sum(matrix_resistances)/len(matrix_resistances)
    return (matrix_resistances, matrix_average, max_voltage_tuple)


def process_matrix_A(float_data, data_handling_logger):
    # R3 is sensor 1, because float data does not have the vrefs
    matrix_A_indexes1 = [1, 2, 4, 7]
    matrix_A_set1, matrix_A_average1, max_A_voltage_1_tuple = get_voltages_resistances_and_average(matrix_A_indexes1, float_data)
    check_deviation(matrix_A_indexes1, matrix_A_set1, matrix_A_average1, ACCEPTABLE_DEVIANCE, data_handling_logger)

    matrix_A_indexes2 = [12, 13, 14, 15]
    matrix_A_set2, matrix_A_average2, max_A_voltage_2_tuple = get_voltages_resistances_and_average(matrix_A_indexes2, float_data)
    check_deviation(matrix_A_indexes2, matrix_A_set2, matrix_A_average2, ACCEPTABLE_DEVIANCE, data_handling_logger)

    matrix_A_indexes3 = [5, 6]
    matrix_A_set3, matrix_A_average3, max_A_voltage_3_tuple = get_voltages_resistances_and_average(matrix_A_indexes3, float_data)
    check_deviation(matrix_A_indexes3, matrix_A_set3, matrix_A_average3, ACCEPTABLE_DEVIANCE, data_handling_logger)

    matrix_A_indexes4 = [9, 10]
    matrix_A_set4, matrix_A_average4, max_A_voltage_4_tuple = get_voltages_resistances_and_average(matrix_A_indexes4, float_data)
    check_deviation(matrix_A_indexes4, matrix_A_set4, matrix_A_average4, ACCEPTABLE_DEVIANCE, data_handling_logger)

    matrix_A_indexes5 = [8, 11]
    matrix_A_set5, matrix_A_average5, max_A_voltage_5_tuple = get_voltages_resistances_and_average(matrix_A_indexes5, float_data)
    check_deviation(matrix_A_indexes5, matrix_A_set5, matrix_A_average5, ACCEPTABLE_DEVIANCE, data_handling_logger)

    matrix_A_values = [(matrix_A_average1, max_A_voltage_1_tuple), (matrix_A_average2, max_A_voltage_2_tuple), (matrix_A_average3, max_A_voltage_3_tuple), (matrix_A_average4, max_A_voltage_4_tuple), (matrix_A_average5, max_A_voltage_5_tuple)]
    return matrix_A_values

def process_matrix_B(float_data, data_handling_logger):
    # R19 is sensor 17, because float data does not have the vrefs
    matrix_B_indexes1 = [17, 18, 20, 23]
    matrix_B_set1, matrix_B_average1, max_B_voltage_1_tuple = get_voltages_resistances_and_average(matrix_B_indexes1, float_data)
    check_deviation(matrix_B_indexes1, matrix_B_set1, matrix_B_average1, ACCEPTABLE_DEVIANCE, data_handling_logger)

    matrix_B_indexes2 = [28, 29, 30, 31]
    matrix_B_set2, matrix_B_average2, max_B_voltage_2_tuple = get_voltages_resistances_and_average(matrix_B_indexes2, float_data)
    check_deviation(matrix_B_indexes2, matrix_B_set2, matrix_B_average2, ACCEPTABLE_DEVIANCE, data_handling_logger)

    matrix_B_indexes3 = [21, 22]
    matrix_B_set3, matrix_B_average3, max_B_voltage_3_tuple = get_voltages_resistances_and_average(matrix_B_indexes3, float_data)
    check_deviation(matrix_B_indexes3, matrix_B_set3, matrix_B_average3, ACCEPTABLE_DEVIANCE, data_handling_logger)

    matrix_B_indexes4 = [25, 26]
    matrix_B_set4, matrix_B_average4, max_B_voltage_4_tuple = get_voltages_resistances_and_average(matrix_B_indexes4, float_data)
    check_deviation(matrix_B_indexes4, matrix_B_set4, matrix_B_average4, ACCEPTABLE_DEVIANCE, data_handling_logger)

    matrix_B_indexes5 = [24, 27]
    matrix_B_set5, matrix_B_average5, max_B_voltage_5_tuple = get_voltages_resistances_and_average(matrix_B_indexes5, float_data)
    check_deviation(matrix_B_indexes5, matrix_B_set5, matrix_B_average5, ACCEPTABLE_DEVIANCE, data_handling_logger)

    matrix_B_values = [(matrix_B_average1, max_B_voltage_1_tuple), (matrix_B_average2, max_B_voltage_2_tuple), (matrix_B_average3, max_B_voltage_3_tuple), (matrix_B_average4, max_B_voltage_4_tuple), (matrix_B_average5, max_B_voltage_5_tuple)]
    return matrix_B_values

def handle_data(data_queue, aref_voltage, adc_resoltuion, stop_threads, vref, iref, output_data_A, output_data_B, output_text_values):
    data_handling_logger=Logger("DATA HANDLING")
    if args.verbose:
        data_handling_logger.set_debug()
    else:
        data_handling_logger.set_error()
    ts = time.time()
    sttime = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d_%H-%M-%S')
    file_name="log_"+sttime+".csv"
    if not os.path.exists(os.path.join(inter_path, "logs")):
        os.makedirs(os.path.join(inter_path, "logs"))
    csv_file = open (os.path.join(inter_path, "logs", file_name), "w", newline="")
    writer=csv.writer(csv_file)
    # VREF_A is taken as sensor0, V_REFB is taken as sensor1
    description_list=["sensor"+str(x) for x in range(MAX_SENSORS)]
    description_list.insert(0, "time")
    writer.writerow(description_list)
    csv_file.close()
    while not stop_threads[0]:
        try:
            data_list = data_queue.get(block=True, timeout=SAMPLING_PERIOD)
            data_queue.task_done()
        except queue.Empty:
            data_handling_logger.warning("Did not recieve measurement data from socket. Replacing with 0's")
            data_list=[0]*MAX_SENSORS
        data_handling_logger.debug(f"{data_list}")
        # First logs everything in csv file
        ts = time.time()
        sttime = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d_%H:%M:%S.%f')[:-3]
        # VREF_A is taken as sensor0
        # VREF_B is taken as sensor1
        vref_a_float = vref[0]
        vref_b_float = vref[1]
        iref_a_float = iref[0]
        iref_b_float = iref[1]
        string_data = [f"{sttime}", f"{vref_a_float:.3f}", f"{vref_b_float:.3f}"]
        float_data = []
        for i in range(MAX_SENSORS-2):
            vread = int_to_voltage(data_list[i+2], aref_voltage, adc_resoltuion)
            vplot = (vread + (R2/R1) * V_A) * (R1/(R1+R2))
            try:
                if args.calculate_values:
                    # Matrix A
                    if i < 16:
                        rsensor = (vplot-vref_a_float)/iref_a_float
                    # Matrix B
                    else:
                        rsensor = (vplot-vref_b_float)/iref_b_float
                    rsensor = rsensor/1E3
                else:
                    rsensor = 1.81*data_list[i+2] - 177
            except ZeroDivisionError:
                rsensor = 0
            string_data.append(f"{rsensor:.3f}")
            float_data.append((vplot, rsensor))
        csv_file = open (os.path.join(inter_path, "logs", file_name), "a", newline="")
        writer=csv.writer(csv_file)
        writer.writerow(string_data)
        csv_file.close()

        # Now separates the values to be shown by fig of matrix A and fig of matrix B
        # This part of the code also takes the averages of the values according to physical proximity in the chip
        matrix_A_values = process_matrix_A(float_data, data_handling_logger)
        matrix_B_values = process_matrix_B(float_data, data_handling_logger)
        matrix_A_B_values = float_data
        try:
            output_data_A.put(matrix_A_values, block=False)
        except queue.Full:
            data_handling_logger.warning("Matrix A data queue is full, dumping measurements")

        try:
            output_data_B.put(matrix_B_values, block=False)
        except queue.Full:
            data_handling_logger.warning("Matrix B data queue is full, dumping measurements")

        try:
            output_text_values.put(matrix_A_B_values, block=False)
        except queue.Full:
            data_handling_logger.warning("Values data queue is full, dumping measurements")

def single_index_to_tuple (i):
    #row = int(i/N_COLS)
    #col = int(i%N_COLS)
    # This can become a class if this mapping needs to be flexible or more elaborate
    if i == 0:
        return (0,0)
    elif i == 1:
        return (0,1)
    elif i == 2 :
        return (1,0)
    elif i == 3 :
        return (1,1)
    elif i == 4 :
        return (1,2)
    else :
        raise NotImplementedError

position_dict = {
# Un-groupped 
    2 : (0.65, 0.1),
    5 : (0.75, 0.1),
    18: (0.85, 0.1),
    21: (0.95, 0.1),
# Un-groupped

# Group 10
    14 : (0.45, 0.9),
    17 : (0.55, 0.9),
    15 : (0.45, 0.8),
    16 : (0.55, 0.8),
# Group 9
    9 : (0.15, 0.9),
    6 : (0.25, 0.9),
    4 : (0.15, 0.8),
    3 : (0.25, 0.8),
# Group 6
    8 : (0.15, 0.7),
    7 : (0.25, 0.7),
# Group 8
    13 : (0.75, 0.7),
    10 : (0.75, 0.6),
# Group 7
    11 : (0.45, 0.7),
    12 : (0.55, 0.7),

# Group 5
    26 : (0.75, 0.4),
    29 : (0.75, 0.5),
# Group 4
    27 : (0.45, 0.4),
    28 : (0.55, 0.4),
# Group 3
    24 : (0.15, 0.4),
    23 : (0.25, 0.4),
# Group 2
    31 : (0.45, 0.3),
    32 : (0.55, 0.3),
    30 : (0.45, 0.2),
    33 : (0.55, 0.2),
# Group 1
    20 : (0.15, 0.3),
    19 : (0.25, 0.3),
    25 : (0.15, 0.2),
    22 : (0.25, 0.2),
}

def calculate_positioning(index):
    return position_dict[index]

def make_animation(data_queue, aref_voltage, adc_resoltuion, vref, iref, stop_threads):
    animation_logger=Logger("ANIMATION")
    if args.verbose:
        animation_logger.set_debug()
    else:
        animation_logger.set_error()
    matrix_A_x_vals={}
    matrix_A_y_vals={}
    matrix_B_x_vals={}
    matrix_B_y_vals={}
    for sensor in range(SENSORS_PER_WINDOW):
        matrix_A_x_vals[sensor]=[]
        matrix_A_y_vals[sensor]=[]
        matrix_B_x_vals[sensor]=[]
        matrix_B_y_vals[sensor]=[]

    matrix_A_title_list=['R3|R5|R6|R9', 'R14|R15|R16|R17', 'R7|R8', 'R11|R12', 'R10|R13']
    figA, axesA, linesA = build_matrix_figure(matrix_A_title_list)
    figA.suptitle("Matrix A", fontsize=16)
    textsA=[]
    matrix_B_title_list=['R19|R20|R22|R25', 'R30|R31|R32|R33', 'R23|R24', 'R27|R28', 'R26|R29']
    figB, axesB, linesB = build_matrix_figure(matrix_B_title_list)
    figB.suptitle("Matrix B", fontsize=16)
    textsB=[]
    figValues, ax = plt.subplots(1,1)
    figValues.suptitle("Individual resistor values", fontsize=16)
    textsValues=[]
    smaller_measured_resistance=[50, 50, 50, 50, 50]
    biggest_measured_resistance=[100, 100, 100, 100, 100]
    output_data_A = queue.Queue(10)
    output_data_B = queue.Queue(10)
    output_text_values = queue.Queue(10)
    try:
        data_handling_thread = threading.Thread(target=handle_data, name="data_handling_thread", args=(data_queue, aref_voltage, adc_resoltuion, stop_threads, vref, iref, output_data_A, output_data_B, output_text_values))
    except Exception as e:
        animation_logger.error("Could not create thread")
        e.with_traceback()
    data_handling_thread.start()

    indexA = count()
    next(indexA)
    indexB = count()
    next(indexB)

    def animateValue(i):
        try:
            # data_list is a list of tuples:
            # [(vplot, resistance)]
            data_list = output_text_values.get(block=True, timeout=SAMPLING_PERIOD)
            output_text_values.task_done()
            voltages = [value[0] for value in data_list]
            resistances = [voltage[1] for voltage in data_list]
        except queue.Empty:
            animation_logger.warning("Did not recieve measurement data for matrix A")
            resistances=[0]*MAX_SENSORS
            voltages=[0]*MAX_SENSORS
        for text in textsValues:
            text.set_visible(False)
        index = 2
        # x_pos, y_pos = (0.15, 0.3)
        for resistance, voltage in zip(resistances, voltages):
            # index+2 is to be coherent with resistance layout naming
            text_value_string = f"R{index}\n{resistance:.3f}\n{voltage:.2f}V"
            x_pos, y_pos = calculate_positioning(index)
            textsValues.append(ax.text(x_pos, y_pos, text_value_string, fontfamily='serif', color='black', fontweight='bold', fontsize='medium', horizontalalignment='right', verticalalignment='top', transform=ax.transAxes))
            index+=1

    def animateA(i):
        try:
            # data_list is a list of tuples:
            # [(resistance, (index, vplot))]
            data_list = output_data_A.get(block=True, timeout=SAMPLING_PERIOD)
            output_data_A.task_done()
            resistances = [value[0] for value in data_list]
            voltage_infos = [voltage_info[1] for voltage_info in data_list]
        except queue.Empty:
            animation_logger.warning("Did not recieve measurement data for matrix A")
            resistances=[0]*MAX_SENSORS
        sample=next(indexA)
        for text in textsA:
            text.set_visible(False)
        for j, line in enumerate(linesA):
            row, col = single_index_to_tuple(j)
            sensor_id=j
            resistance = resistances[sensor_id]
            index, voltage = voltage_infos[sensor_id]
            max_voltage_string = f"R{index+2}: {voltage:.2f}V"
            if (voltage > SATURATION_VOLTAGE) :
                textsA.append(axesA[row][col].text(0.35, 1.1, max_voltage_string, color='red', fontweight='bold', fontsize='medium', horizontalalignment='right', verticalalignment='top', transform=axesA[row][col].transAxes))
            elif (voltage > CAUTION_VOLTAGE):
                textsA.append(axesA[row][col].text(0.35, 1.1, max_voltage_string, color='orange', fontweight='bold', fontsize='medium', horizontalalignment='right', verticalalignment='top', transform=axesA[row][col].transAxes))
            else:
                textsA.append(axesA[row][col].text(0.35, 1.1, max_voltage_string, color='black', fontweight='bold', fontsize='medium', horizontalalignment='right', verticalalignment='top', transform=axesA[row][col].transAxes))
            if resistance < 0:
                animation_logger.debug("Negative resistance!")
            text = f"{resistance:.3f}"
            textsA.append(axesA[row][col].text(1, 1.1, text, fontweight='bold', fontsize='medium', horizontalalignment='right', verticalalignment='top', transform=axesA[row][col].transAxes))
            if smaller_measured_resistance[sensor_id] <= 50 or (resistance > 50 and resistance < smaller_measured_resistance[sensor_id]):
                smaller_measured_resistance[sensor_id] = resistance - 50
            if resistance > biggest_measured_resistance[sensor_id]:
                biggest_measured_resistance[sensor_id] = resistance + 50
            
            matrix_A_x_vals[sensor_id].append(sample)
            matrix_A_y_vals[sensor_id].append(resistance)

            axesA[row][col].set_xlim(0, sample)
            axesA[row][col].set_ylim(smaller_measured_resistance[sensor_id], biggest_measured_resistance[sensor_id])
            line.set_data(matrix_A_x_vals[sensor_id], matrix_A_y_vals[sensor_id])
        return linesA

    def animateB(i):
        try:
            data_list = output_data_B.get(block=True, timeout=SAMPLING_PERIOD)
            output_data_B.task_done()
            resistances = [value[0] for value in data_list]
            voltage_infos = [voltage_info[1] for voltage_info in data_list]
        except queue.Empty:
            animation_logger.warning("Did not recieve measurement data for matrix B")
            resistances=[0]*MAX_SENSORS
        sample=next(indexB)
        for text in textsB:
            text.set_visible(False)
        for j, line in enumerate(linesB):
            row, col = single_index_to_tuple(j)
            sensor_id=j
            resistance = resistances[sensor_id]
            index, voltage = voltage_infos[sensor_id]
            max_voltage_string = f"R{index+2}: {voltage:.2f}V"
            if (voltage > SATURATION_VOLTAGE) :
                textsB.append(axesB[row][col].text(0.35, 1.1, max_voltage_string, color='red', fontweight='bold', fontsize='medium', horizontalalignment='right', verticalalignment='top', transform=axesB[row][col].transAxes))
            elif (voltage > CAUTION_VOLTAGE):
                textsB.append(axesB[row][col].text(0.35, 1.1, max_voltage_string, color='orange', fontweight='bold', fontsize='medium', horizontalalignment='right', verticalalignment='top', transform=axesB[row][col].transAxes))
            else:
                textsB.append(axesB[row][col].text(0.35, 1.1, max_voltage_string, color='black', fontweight='bold', fontsize='medium', horizontalalignment='right', verticalalignment='top', transform=axesB[row][col].transAxes))
            if resistance < 0:
                animation_logger.debug("Negative resistance!")
            text = f"{resistance:.3f}"
            textsB.append(axesB[row][col].text(1, 1.1, text, fontweight='bold', fontsize='medium', horizontalalignment='right', verticalalignment='top', transform=axesB[row][col].transAxes))
            if smaller_measured_resistance[sensor_id] <= 50 or (resistance > 50 and resistance < smaller_measured_resistance[sensor_id]):
                smaller_measured_resistance[sensor_id] = resistance - 50
            if resistance > biggest_measured_resistance[sensor_id]:
                biggest_measured_resistance[sensor_id] = resistance + 50
            
            matrix_B_x_vals[sensor_id].append(sample)
            matrix_B_y_vals[sensor_id].append(resistance)

            axesB[row][col].set_xlim(0, sample)
            axesB[row][col].set_ylim(smaller_measured_resistance[sensor_id], biggest_measured_resistance[sensor_id])
            line.set_data(matrix_B_x_vals[sensor_id], matrix_B_y_vals[sensor_id])
        return linesB

    animA=animation.FuncAnimation(figA, animateA, blit=False, cache_frame_data=False, interval=SAMPLING_PERIOD*1E3)
    animB=animation.FuncAnimation(figB, animateB, blit=False, cache_frame_data=False, interval=SAMPLING_PERIOD*1E3)
    animValues=animation.FuncAnimation(figValues, animateValue, blit=False, cache_frame_data=True, interval=SAMPLING_PERIOD*1E3)
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
        data_queue.put([0]*34)
        vref=[0, 0]
        iref=[0, 0]
        try:
            retriever_thread = threading.Thread(target=retrieve_measurement_data, name="retriever_thread", args=(data_queue, aref_voltage, adc_resoltuion, stop_threads, conn, vref, iref))
        except Exception as e:
            gui_monitor_logger.error("Could not create thread")
            e.with_traceback()
        retriever_thread.start()

        make_animation(data_queue, aref_voltage, adc_resoltuion, vref, iref, stop_threads)

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
        conn.close()
        serial_server.close()
        gui_monitor_logger.debug("Bye")
    except Exception as e:
        e.with_traceback()
    exit(0)
