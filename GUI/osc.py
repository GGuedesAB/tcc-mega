import serial
import serial.tools.list_ports
import numpy
import os
import sys
import matplotlib.pyplot as plot
import matplotlib.animation as animation
import time
import subprocess
import queue
import threading
import logging
import socket
import argparse
inter_path=os.path.dirname(os.path.realpath(__file__))
sys.path.append(inter_path)
from logger import Logger


parser = argparse.ArgumentParser(description='Serial monitor script. Creates a socket and sends data read from serial input there.')
parser.add_argument('--port', help='Port to make serial connection', type=str, required=True)
parser.add_argument('--nsensors', help='Number of sensors that will be monitored', type=int, required=True)
parser.add_argument('--baud', help='Baud rate of serial connection', type=int, default=115200)
parser.add_argument('--verbose', help='Outputs all messages', action='store_true')
args = parser.parse_args()

class Oscilloscope ():
    def __init__ (self, config):
        self.port = config['port']
        self.baud = config['baud']
        self.num_sensors = config['sensors']
        self.sample_buffer = numpy.zeros(self.num_sensors)
        self.logger = Logger("SERIAL")
        if args.verbose:
            self.logger.set_debug()
        else:
            self.logger.set_info()
        self.sample = 0
        try:
            self.ser = serial.Serial(port=self.port, baudrate=self.baud)
            self.connected=True
        except:
            self.logger.error ('Could not connect to serial port ' + self.port)
            available_ports = serial.tools.list_ports.comports()
            self.logger.info (f"List of available ports")
            for p in available_ports:
                self.logger.info (f"\t{p}")
            exit(1)

    # Returns a copy of the object's internal buffer
    def get_serial_data (self):
        success_read = False
        while not success_read:
            try:
                data = self.ser.read_until('\n'.encode('utf-8'))
            except serial.SerialException:
                self.logger.warning ('Lost connection on port ' + self.port)
                self.connected = False
                # If connection is lost, will keep trying to reconnect
                while not self.connected:
                    try:
                        self.ser = serial.Serial(port=self.port, baudrate=self.baud)
                        self.connected=True
                        self.logger.warning ('Re-gained connection on port ' + self.port)
                    except serial.SerialException:
                        self.connected = False
            try:
                data = data.decode('utf-8')
                data = data.rsplit('|')
                data.remove('\r\n')
                data = numpy.array(data)
                data = numpy.flip(data)
                for i in range(self.num_sensors):
                    self.sample_buffer[i] = int(data[i])
                success_read = True
            except:
                success_read = False
        return numpy.copy(self.sample_buffer)

def produce_window(measurement_queue, ser):
    producer_logger = Logger("SOCKET-PUT")
    if args.verbose:
        producer_logger.set_debug()
    else:
        producer_logger.set_error()
    while True:
        measurement_buffer=ser.get_serial_data()
        try:
            measurement_queue.put(measurement_buffer, block=False)
        except queue.Full:
            producer_logger.warning("Measurement queue is full, dumping new measurements")
        except KeyboardInterrupt:
            return

def consume_reading(measurement_queue, num_sensors):
    consumer_logger = Logger("SOCKET-SEND")
    if args.verbose:
        consumer_logger.set_debug()
    else:
        consumer_logger.set_error()
    server_addr=('localhost', 25565)
    serial_server = socket.socket()
    serial_server.bind(server_addr)
    serial_server.listen(1)
    conn, addr = serial_server.accept()
    consumer_logger.info(f"Connected to {addr}")
    while True:
        try:
            measurement_buffer = measurement_queue.get(block=True, timeout=0.1)
            measurement_queue.task_done()
        except queue.Empty:
            consumer_logger.warning("Measurement readings are out of sync")
            measurement_buffer = numpy.zeros(num_sensors)
        except KeyboardInterrupt:
            return
        try:
            measurement_string="<"
            for measurement in measurement_buffer:
                measurement_int = int(measurement)
                measurement_string+=f"|{measurement_int:04d}|"
            measurement_string+=">"
            conn.sendall(measurement_string.encode("utf-8"))
        except:
            consumer_logger.error("Could not send message on socket")

if __name__ == "__main__":
    oscilloscope_logger = Logger("OSC-MAIN")
    if args.verbose:
        oscilloscope_logger.set_debug()
    else:
        oscilloscope_logger.set_error()
    config={
        'port' : args.port,
        'baud' : args.baud,
        'sensors' : args.nsensors,
    }
    oscilloscope_logger.debug(f"Starting serial communication with: {config}")
    # Create two threads one for serial comm and one for oscilloscope
    #   These threads will communicate through a queue that contains buffers
    #       Each buffer has a 16x1024 window
    #   Ideally one item should be put and consumed every 0.1s
    #   Queue must warn if more than one buffer is present
    #       Queue can store a max of 10 windows
    window_queue = queue.Queue(1024)
    serial_reader = Oscilloscope(config)
    try:
        producer_thread = threading.Thread(target=produce_window, name="producer_thread", args=(window_queue, serial_reader))
        consumer_thread = threading.Thread(target=consume_reading, name="consumer_thread", args=(window_queue, serial_reader.num_sensors))
    except Exception as e:
        oscilloscope_logger.error("Could not create threads")
        e.with_traceback()
    producer_thread.start()
    consumer_thread.start()
    window_queue.join()

    #print(my_osc.sample_buffer)
    #exit(0)
