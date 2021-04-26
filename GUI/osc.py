import serial
import numpy
import os
import matplotlib.pyplot as plot
import matplotlib.animation as animation
import time
import subprocess
import queue
import threading
import logging
import socket

class Logger ():
    def __init__ (self):
        self.log_format = "[%(name)s] %(levelname)s: %(message)s"
        self.date_format = '%d-%m-%Y %H:%M:%S'
        self.logger = logging.getLogger(__name__)
    def set_debug(self):
        logging.basicConfig(level=logging.DEBUG, format=self.log_format, datefmt=self.date_format)

    def set_info(self):
        logging.basicConfig(level=logging.INFO, format=self.log_format, datefmt=self.date_format)

    def set_warning(self):
        logging.basicConfig(level=logging.WARNING, format=self.log_format, datefmt=self.date_format)

    def set_error(self):
        logging.basicConfig(level=logging.ERROR, format=self.log_format, datefmt=self.date_format)

    def error(self, msg):
        logging.error(msg)
    
    def debug(self, msg):
        logging.debug(msg)

    def info(self, msg):
        logging.info(msg)

    def warning(self, msg):
        logging.warning(msg)

class Oscilloscope ():
    def __init__ (self, config):
        self.port = config['port']
        self.baud = config['baud']
        self.num_sensors = config['sensors']
        self.sample_buffer = numpy.zeros(self.num_sensors)
        self.logger = Logger()
        self.logger.set_warning()
        self.sample = 0
        try:
            self.ser = serial.Serial(port=self.port, baudrate=self.baud)
        except:
            self.logger.error ('Could not connect to serial port ' + self.port)

    # Returns a copy of the object's internal buffer
    def get_serial_data (self):
        success_read = False
        while not success_read:
            try:
                data = self.ser.read_until('\n'.encode('utf-8'))
                data = data.decode('utf-8')
                data = data.rsplit('|')
                data.remove('\r\n')
                self.logger.debug(f"Recieved {data}")
                data = numpy.array(data)
                for i in range(self.num_sensors):
                    self.sample_buffer[i] = int(data[i])
                success_read = True
            except:
                success_read = False
        return numpy.copy(self.sample_buffer)

def produce_window(measurement_queue, ser):
    producer_logger = Logger()
    producer_logger.set_warning()
    while True:
        measurement_buffer=ser.get_serial_data()
        try:
            measurement_queue.put(measurement_buffer, block=False)
        except queue.Full:
            print("[PRODUCER] WARNING: Measurement queue is full, dumping new measurement.")
        except KeyboardInterrupt:
            return

def consume_reading(measurement_queue, num_sensors):
    consumer_logger = Logger()
    consumer_logger.set_warning()
    server_addr=("localhost", 25565)
    serial_server = socket.socket()
    serial_server.bind(server_addr)
    serial_server.listen()
    conn, addr = serial_server.accept()
    print(f"[CONSUMER] INFO: Connected to {addr}")
    while True:
        try:
            measurement_buffer = measurement_queue.get(block=True, timeout=0.1)
            measurement_queue.task_done()
        except queue.Empty:
            print("[CONSUMER] WARNING: Measurement readings are out of sync.")
            measurement_buffer = numpy.zeros(num_sensors)
        except KeyboardInterrupt:
            return
        #print("[CONSUMER] INFO: Readings")
        try:
            measurement_string="<"
            for measurement in measurement_buffer:
                measurement_int = int(measurement)
                measurement_string+=f"|{measurement_int:04d}|"
            measurement_string+=">"
            conn.sendall(measurement_string.encode("utf-8"))
        except:
            print("[CONSUMER] ERROR: Could not send message on socket.")
            exit(1)
    serial_server.close()

if __name__ == "__main__":
    config={
        'port' : "COM10",
        'baud' : 115200,
        'adc_res' : 10,
        'sensors' : 2,
        'samples' : 1024
    }
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
        print("[MAIN] ERROR: Could not create threads")
        e.with_traceback()
    producer_thread.start()
    consumer_thread.start()
    window_queue.join()

    #print(my_osc.sample_buffer)
    #exit(0)
