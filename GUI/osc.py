import serial
import numpy
import os
import matplotlib.pyplot as plot
import matplotlib.animation as animation
import time

class Oscilloscope ():
    def __init__ (self, config):
        self.port = config['port']
        self.baud = config['baud']
        self.voltage_ref = config['aref']
        self.num_sensors = config['sensors']
        self.buffer_size = config['samples']
        self.ADC_resolution = 1023
        self.sample_buffer = numpy.zeros(self.num_sensors * self.buffer_size)
        self.sample_buffer = self.sample_buffer.reshape(self.num_sensors, self.buffer_size)
        self.sample = 0
        try:
            self.ser = serial.Serial(port=self.port, baudrate=self.baud)
        except:
            print ('ERROR: Could not connect to serial port ' + self.port)
            exit(1)

    def get_serial_data (self):
        success_read = False
        while not success_read:
            try:
                data = self.ser.read_until('\n'.encode('utf-8'))
                data = data.decode('utf-8')
                data = data.rsplit('|')
                data.remove('\r\n')
                data = numpy.array(data)
                for i in range(self.num_sensors):
                    analog_value = float( (int(data[i])*self.voltage_ref) / self.ADC_resolution)
                    self.sample_buffer[i][self.sample] = analog_value
                self.sample = (self.sample % self.buffer_size) + 1
                success_read = True
            except KeyboardInterrupt:
                print('ERROR: Giving up reading!')
                exit(0)
            except:
                success_read = False

    def get_voltage (self):
        if self.unformatted_voltage:
            identifier = 'V'
            self.voltage = self.unformatted_voltage.rsplit('|')
            self.voltage.remove(identifier)
            self.voltage.pop()
            result = list(map(int, self.voltage))
        else:
            result = self.zeroes
        yield result

    def get_current (self):
        if self.unformatted_current:
            identifier = 'I'
            self.current = self.unformatted_current.rsplit('|')
            self.current.remove(identifier)
            self.current.pop()
            result = list(map(int, self.current))
        else:
            result = self.zeroes
        yield result

    def get_instant_power (self):
        instant_power = [voltage*current for voltage,current in zip(self.voltage, self.current)]
        yield instant_power

    def gen_voltage_line (self, data):
        try:
            self.get_serial_data()
        except ValueError:
            self.unformatted_voltage = ''
            self.unformatted_current = ''
            self.unformatted_temperature = ''
            self.unformatted_light = ''

        if (len(data) != self.number_of_samples):
            print ('WARNING: Communication error!')
            data = self.zeroes
        line1.set_data(self.data_range, data)

    def gen_current_line (self, data):
        if (len(data) != self.number_of_samples):
            print ('WARNING: Communication error!')
            data = self.zeroes
        line2.set_data(self.data_range, data)

    def gen_temperature_line (self, data):
        if (len(data) != self.number_of_samples):
            print ('WARNING: Communication error!')
            data = self.zeroes
        line3.set_data(self.data_range, data)
        
    #def gen_light_line (self, data):
    #    if (len(data) != self.number_of_samples):
    #        print ('WARNING: Communication error!')
    #        data = self.zeroes
    #    line4.set_data(self.data_range, data)

if __name__ == "__main__":
    # my_osc = Oscilloscope()
    # print ('Started monitor.')
    # fig, ((ax1, ax2), (ax3,ax4)) = plot.subplots(2,2)
    
    # line1, = ax1.plot(my_osc.data_range, my_osc.zeroes)
    
    # line2, = ax2.plot(my_osc.data_range, my_osc.zeroes)
    
    # line3, = ax3.plot(my_osc.data_range, my_osc.zeroes)
    
    # line4, = ax4.plot(my_osc.data_range, my_osc.zeroes)
    
    # ax1.set_xlim(0, 400)
    # ax1.set_ylim(-1, 1100)
    # ax1.set_title('Tensão (V)')
    
    # ax2.set_xlim(0, 400)
    # ax2.set_ylim(-1, 1100)
    # ax2.set_title('Corrente (A)')
    
    # ax3.set_xlim(0, 400)
    # ax3.set_ylim(-1, 1100)
    # ax3.set_title('Potência instantânea (W)')

    # ani1 = animation.FuncAnimation(fig=fig, func=my_osc.gen_voltage_line, frames=my_osc.get_voltage, interval=50)
    # ani2 = animation.FuncAnimation(fig=fig, func=my_osc.gen_current_line, frames=my_osc.get_current, interval=50)
    # ani3 = animation.FuncAnimation(fig=fig, func=my_osc.gen_temperature_line, frames=my_osc.get_temperature, interval=50)

    #plot.show()

    config={
        'port' : "COM10",
        'baud' : 115200,
        'aref' : 5.15,
        'sensors' : 16,
        'samples' : 1024
    }
    my_osc = Oscilloscope(config)
    while True:
        start_time = time.time()
        my_osc.get_serial_data()
        print(f"{start_time-time.time()}")

    #print(my_osc.sample_buffer)
    #exit(0)
