import serial
import serial.tools.list_ports
import numpy
import os
import sys
import matplotlib.pyplot as plot
import matplotlib.animation as animation
import queue
import threading
import socket
import argparse
import signal
import time
inter_path=os.path.dirname(os.path.realpath(__file__))
sys.path.append(inter_path)
from logger import Logger

# In seconds
DELTA=0.1
SAMPLING_PERIOD=10+DELTA

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

    def close (self):
        self.ser.close()

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

def produce_window(measurement_queue, ser, stop):
    producer_logger = Logger("SOCKET-PUT")
    if args.verbose:
        producer_logger.set_debug()
    else:
        producer_logger.set_error()
    while not stop[0]:
        old_time = time.time()
        measurement_buffer=ser.get_serial_data()
        try:
            measurement_queue.put(measurement_buffer, block=False)
            producer_logger.debug(f"Delta: {time.time()-old_time:.3f}s")
        except queue.Full:
            producer_logger.warning("Measurement queue is full, dumping new measurements")
    ser.close()
    producer_logger.debug("Bye")
    exit(0)

def consume_reading(measurement_queue, num_sensors, stop):
    consumer_logger = Logger("SOCKET-SEND")
    if args.verbose:
        consumer_logger.set_debug()
    else:
        consumer_logger.set_error()
    connection_addr=('localhost', 25565)
    try:
        data_socket = socket.socket()
        data_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        data_socket.connect(connection_addr)
    except socket.timeout:
        consumer_logger.error("Could not connect")
        return
    except ConnectionRefusedError:
        consumer_logger.error("Could not connect")
        return
    while not stop[0]:
        try:
            measurement_buffer = measurement_queue.get(block=True, timeout=SAMPLING_PERIOD)
            measurement_queue.task_done()
        except queue.Empty:
            consumer_logger.warning("Measurement readings are out of sync")
            measurement_buffer = numpy.zeros(num_sensors)
        try:
            measurement_string="<"
            for measurement in measurement_buffer:
                measurement_int = int(measurement)
                measurement_string+=f"|{measurement_int:04d}|"
            measurement_string+=">"
            data_socket.send(measurement_string.encode("utf-8"))
        except:
            consumer_logger.error("Could not send message on socket")
    data_socket.close()
    consumer_logger.debug("Bye")
    exit(0)

if __name__ == "__main__":
    stop_threads=[False]
    oscilloscope_logger = Logger("OSC")
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
        producer_thread = threading.Thread(target=produce_window, name="producer_thread", args=(window_queue, serial_reader, stop_threads))
        consumer_thread = threading.Thread(target=consume_reading, name="consumer_thread", args=(window_queue, serial_reader.num_sensors, stop_threads))
    except Exception as e:
        oscilloscope_logger.error("Could not create threads")
        exit(1)
    
    def handler(signum, frame):
        oscilloscope_logger.info("Killing threads")
        stop_threads[0]=True
        producer_thread.join()
        consumer_thread.join()
        exit(0)
    
    signal.signal(signal.SIGINT, handler)

    producer_thread.start()
    consumer_thread.start()
    producer_thread.join()
    consumer_thread.join()
    window_queue.join()