#!/usr/bin/env python3
# -*-
"""
    class Amod to
    - read analog tension on two digital pins
    - calibrate the sensor
    - plot the measured data's
"""
import time
import RPi.GPIO as GPIO
import math
import numpy as np
import scipy.stats as stat
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import pdb

class Amod:
    
    def __init__(self, pin_cmd_bat = 8, pin_mes_bat = 10, pin_cmd_out = 12, pin_mes_out = 16, from_who = ""):
        
        # version infos
        VERSION_NO = "0.01.01" 
        VERSION_DATE = "27.11.2020"
        VERSION_DESCRIPTION = "prototype"
        VERSION_STATUS = "initial version"
        VERSION_AUTEUR = "josmet"
#         
#         self.pin_cmd = 8 # control pin
#         self.pin_mes = 10 # measure pin
  
        GPIO.setmode(GPIO.BOARD)
        GPIO.setwarnings(False)
        GPIO.setup(pin_cmd_bat, GPIO.OUT)  # initialize control pin                  
        GPIO.setup(pin_mes_bat, GPIO.IN)  # initialize measure pi (attention no pull-up or pull-down)
        GPIO.setup(pin_cmd_out, GPIO.OUT)  # initialize control pin                  
        GPIO.setup(pin_mes_out, GPIO.IN)  # initialize measure pi (attention no pull-up or pull-down)
        GPIO.add_event_detect(pin_mes_bat, GPIO.FALLING, callback=self.interrupt_management) 
        GPIO.add_event_detect(pin_mes_out, GPIO.FALLING, callback=self.interrupt_management) 
        GPIO.output(pin_cmd_bat, GPIO.LOW) 
        GPIO.output(pin_cmd_out, GPIO.LOW) 

#         pdb.set_trace()
#         # test pins cmd and mes 
#         pdb.set_trace()
#         GPIO.output(self.pin_cmd, GPIO.LOW) 
#         print(GPIO.input(self.pin_mes))
#         GPIO.output(self.pin_cmd, GPIO.HIGH) 
#         print(GPIO.input(self.pin_mes))
        
        
#         self.t_discharge = 250e-6 # time to discharge the capacitor
        self.t_end_mesure = 0.0
        self.t_start_mesure = 0.0
        self.end_requierd = False
#         self.int_resp_time = 4.95e-3
#         self.VCEsat = 10e-3 # pour déduire la tension de saturation du transistor
#         self.v_timeout = 1
#         self.v_tol = 2.5 / 100 # 2.5 %
        self.filter = 1.5 # +/- n ecart types gardés
        self.v_val = []
        self.n_moy = 50


        if from_who != "calibration": # if not in calibration read the ini data 
            with open('amod_555.ini', 'r') as ini_file:
                data = ini_file.readlines()
                params = data[0].split(",")
                self.u_in_trig = float(params[0]) # the input trigger level (depend on the harware)
                self.R1 = float(params[1]) # value of the resistor
                self.C1 = float(params[2]) # value of the capacitor
                self.int_resp_time = float(params[3]) # interrupt response time
                
        #Set up plot
        self.figure, self.ax = plt.subplots(2)
        # plot [0]
        self.lines_0, = self.ax[0].plot([],[], 'r-')
        #Autoscale on unknown axis and known lims on the other
        self.ax[0].set_autoscaley_on(True)
        self.ax[0].xaxis.set_major_formatter(mdates.DateFormatter('%d.%m.%Y %H:%M:%S'))
        self.ax[0].set_title("battery monitoring")
        self.ax[0].set_ylabel("Tension [V]")
        # Format the x-axis for dates (label formatting, rotation)
        self.figure.autofmt_xdate(rotation=45)
        #Other stuff
        self.ax[0].grid()
        
        # plot [1]
        self.lines_1, = self.ax[1].plot([],[], 'b-')
        #Autoscale on unknown axis and known lims on the other
        self.ax[1].set_autoscaley_on(True)
        self.ax[1].xaxis.set_major_formatter(mdates.DateFormatter('%d.%m.%Y %H:%M:%S'))
        self.ax[1].set_title("VCC monitoring")
        self.ax[1].set_ylabel("Tension [V]")
        # Format the x-axis for dates (label formatting, rotation)
        self.figure.autofmt_xdate(rotation=45)
        #Other stuff
        self.ax[1].grid()

    def add_point(self, xdata, ydata_bat, ydata_out):
        #Update data (with the new _and_ the old points)
        
        self.lines_0.set_xdata(xdata)
        self.lines_0.set_ydata(ydata_bat)
        #Need both of these in order to rescale
        self.ax[0].relim()
        self.ax[0].autoscale_view()
        #We need to draw *and* flush
        self.figure.canvas.draw()
        self.figure.canvas.flush_events()
        
        self.lines_1.set_xdata(xdata)
        self.lines_1.set_ydata(ydata_out)
        #Need both of these in order to rescale
        self.ax[1].relim()
        self.ax[1].autoscale_view()
        #We need to draw *and* flush
        self.figure.canvas.draw()
        self.figure.canvas.flush_events()
        
    def get_tension(self, n_moyenne, pin_cmd = 8, pin_mes = 10, show_histogram = False):

        GPIO.output(pin_cmd, GPIO.HIGH) # décharger le condensateur

        j = 0
        l_elapsed = []
        pulse_width = 10e-6
        t_pause_between_mesures = 10e-3
        t_timeout = 1
        VCEsat = 15e-3
        while j < n_moyenne:
            
            time.sleep(t_pause_between_mesures) # laisser du temps pour décharger le condo
            
            self.end_requierd = False
            GPIO.output(pin_cmd, GPIO.LOW) # déclancher la mesure (NE555 -> TRIG passe à 0)
            time.sleep(pulse_width)
            GPIO.output(pin_cmd, GPIO.HIGH) # déclancher la mesure (NE555 -> TRIG passe à 0)
            self.t_start_mesure = time.time() # déclancher le chrono
            while not self.end_requierd:
                if time.time() - self.t_start_mesure > t_timeout:
                    stop_requierd = True
                    print("interruption manquée")
                    
            elapsed = (self.t_end_mesure - self.t_start_mesure) - self.int_resp_time
            l_elapsed.append(elapsed)
            time.sleep(t_pause_between_mesures)
            j += 1
        GPIO.output(pin_cmd, GPIO.LOW) # déclancher la décharge du condensateur
        
        # get stats of data list
        nx, mmx, mx, vx, skx, ktx = stat.describe(l_elapsed)
        # filter the data list
        df = pd.DataFrame(l_elapsed, columns=list('B'))
        l_ref_filtered = df[((df.B - df.B.mean()) / df.B.std()).abs() < self.filter]
        l_ref_filtered_mean = l_ref_filtered.B.mean()

        # create ans show histogramm
        if show_histogram:
            l_tension = []
            for v in l_elapsed:
                l_tension.append(self.u_in_trig / (1 - math.exp(- v / (self.R1 * self.C1))) - VCEsat)
                
            df1 = pd.DataFrame(l_tension, columns=list('B'))
            l_tension_filtered = df1[((df1.B - df1.B.mean()) / df1.B.std()).abs() < self.filter]
            l_tension_filtered_mean = l_tension_filtered.B.mean()
        
            # plot histogramm
            n, bins, patches = plt.hist(x=l_tension, bins=min(int(n_moyenne/2),50), color='#0504aa', alpha=0.7, rwidth=0.85)
            plt.hist(x=l_tension_filtered, bins=bins, color='#ffff00', alpha=0.7, rwidth=0.85)
            plt.grid(axis='y', alpha=0.75)
            plt.xlabel('Avg = ' + '{:.3f}'.format(l_tension_filtered_mean))
            plt.ylabel('Frequency')
            plt.title("Filtered on " + str(self.filter) + " standard deviation")
            plt.text(23, 45, r'$\mu=15, b=3$')
            maxfreq = n.max()
            # Set a clean upper y-axis limit.
            plt.ylim(ymax=np.ceil(maxfreq/10) *10 if maxfreq % 10 else maxfreq + 10)
            # insert a legend
            blue_patch = mpatches.Patch(color='#0504aa', label='excluded')
            yellow_patch = mpatches.Patch(color='#ffff00', label='used for avg')
            plt.legend(handles=[blue_patch, yellow_patch])

            plt.show()
            
        u_average = self.u_in_trig / (1 - math.exp(- l_ref_filtered_mean / (self.R1 * self.C1)))
        return u_average
    
    def get_response_time(self, show_histogram = False):

        self.v_val.clear()
        i = 0
        self.end_requierd = False
        GPIO.output(self.pin_cmd, GPIO.HIGH) 
        while i < self.n_moy:
            time.sleep(20e-6)
            self.t_start_mesure = time.time()
            GPIO.output(self.pin_cmd, GPIO.LOW) 
            while not self.end_requierd:
                pass
            elapsed = (self.t_end_mesure - self.t_start_mesure)
            GPIO.output(self.pin_cmd, GPIO.HIGH) 
            self.end_requierd = False
            self.v_val.append(elapsed)
            i += 1
        
        # get stats of data list
        nx, mmx, mx, vx, skx, ktx = stat.describe(self.v_val)
        # filter the data list
        df = pd.DataFrame(self.v_val, columns=list('B'))
        val_filtered = df[((df.B - df.B.mean()) / df.B.std()).abs() < self.filter]
        val_filtered_mean = val_filtered.B.mean()

        # create ans show histogramm
        if show_histogram:
        
            # plot histogramm
            n, bins, patches = plt.hist(x=self.v_val, bins=min(int(self.n_moy),50), color='#0504aa', alpha=0.7, rwidth=0.85)
            plt.hist(x=val_filtered, bins=bins, color='#ffff00', alpha=0.7, rwidth=0.85)
            plt.grid(axis='y', alpha=0.75)
            plt.xlabel('Avg = ' + '{:.3f}'.format(val_filtered_mean*1e3) + " ms")
            plt.ylabel('Frequency')
            plt.title("Filtered on " + str(self.filter) + " standard deviation")
            plt.text(23, 45, r'$\mu=15, b=3$')
            maxfreq = n.max()
            # Set a clean upper y-axis limit.
            plt.ylim(ymax=np.ceil(maxfreq/10) *10 if maxfreq % 10 else maxfreq + 10)
            # insert a legend
            blue_patch = mpatches.Patch(color='#0504aa', label='excluded')
            yellow_patch = mpatches.Patch(color='#ffff00', label='used for avg')
            plt.legend(handles=[blue_patch, yellow_patch])

            plt.show()
            
        GPIO.cleanup()
        return val_filtered_mean
    
    def interrupt_management(self, channel):
        self.t_end_mesure = time.time()
        self.end_requierd = True

if __name__ == '__main__':

    #verify tension and filtering
    amod = Amod()
    a = amod.get_tension(20, 8, 10, show_histogram = True)
    b = amod.get_tension(20, 12, 16, show_histogram = True)
#     amod.test_ne555()
    
    GPIO.cleanup()

        

