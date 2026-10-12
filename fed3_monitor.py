import serial
import time
import csv
import os
import re
import argparse
import glob
import matplotlib.pyplot as plt
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CONNECTION CONFIGURATION ---
SERIAL_PORT = '/dev/cu.usbmodem12301'  
BAUD_RATE = 115200    
# --------------------------------

# --- EMAIL ALERT CONFIGURATION ---
SENDER_EMAIL = "carterbower00@gmail.com"     # The email sending the alert
SENDER_APP_PASSWORD = "jzln pfbj gimp fmgg"        # The 16-character App Password (no spaces needed)
RECEIVER_EMAIL = "carter_bower@berkeley.edu"       # Where the alert goes
# --------------------------------

# --- ACTOGRAM CONFIGURATION ---
BIN_MINUTES = 10        
LIGHT_START = 7         
DARK_START = 19         
# ------------------------------

def send_email_alert(subject, body):
    """Logs into the email server and sends a notification."""
    print("Attempting to send email alert...")
    try:
        # Construct the email structure
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECEIVER_EMAIL
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        # Connect to Gmail's server securely
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()  
        server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"Alert email successfully sent to {RECEIVER_EMAIL}!")
    except Exception as e:
        print(f"Failed to send email alert. Error: {e}")

def log_live_data():
    """Monitors the serial port and records incoming data to a new timestamped CSV file."""
    session_time = time.strftime("%Y-%m-%d_%H-%M-%S")
    data_file = f"fed3_data_{session_time}.csv"
    
    # Cooldown flag so we don't spam emails if the machine stays jammed
    has_sent_jam_email = False 
    
    print(f"Connecting to FED3 on {SERIAL_PORT}...")
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)
        print(f"Connected successfully!")
        print(f"Saving data continuously to: '{data_file}'...")
        print("Listening for data... (DO NOT CLOSE THIS TERMINAL)\n")
        
        with open(data_file, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Pellet_Count"])
            
            while True:
                if ser.in_waiting > 0:
                    raw_line = ser.readline()
                    line = raw_line.decode('utf-8', errors='ignore').strip()
                    
                    if line:
                        print(f"[Device Output] {line}")
                        match = re.search(r'Pellet_Count[:\s,]*(\d+)', line, re.IGNORECASE)
                        
                        if match:
                            pellet_count = int(match.group(1))
                            pc_timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                            
                            writer.writerow([pc_timestamp, pellet_count])
                            f.flush()  
                            print(f"Logged: {pc_timestamp} -> Pellet Count: {pellet_count}")
                            
                        # === JAM DETECTION ===
                        if "Jam" in line or "jammed" in line.lower():
                            print("ALERT: A machine jam event was reported!")
                            if not has_sent_jam_email:
                                subject = "FED3 ALERT: Machine Jammed!"
                                body = f"Your FED3 device reported a jam at {time.strftime('%Y-%m-%d %H:%M:%S')}.\n\nPlease check the enclosure to clear the blockage and reset the device."
                                send_email_alert(subject, body)
                                has_sent_jam_email = True  # Locks the email trigger so it only sends once

    # === CONNECTION LOSS DETECTION ===
    except (serial.SerialException, OSError) as e:
        error_time = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"\nFATAL ERROR: Lost connection to FED3. Device vanished from {SERIAL_PORT}.")
        
        # Send the disconnect email
        subject = "FED3 ALERT: Connection Lost!"
        body = f"Python lost USB connection with the FED3 device at {error_time}.\n\nError Details: {e}\n\nThe script has stopped logging data. Please check the physical USB cable and restart the Python monitor."
        send_email_alert(subject, body)
        
    except KeyboardInterrupt:
        print(f"\nLive monitor gracefully stopped by user. Data is safe in '{data_file}'.")

def get_latest_data_file():
    """Finds the most recently created FED3 CSV file in the current folder."""
    list_of_files = glob.glob("fed3_data_*.csv")
    if not list_of_files:
        return None
    return max(list_of_files, key=os.path.getctime)

def generate_graph():
    """Reads the newest CSV file, calculates frequency, and generates a circadian actogram."""
    data_file = get_latest_data_file()
    
    if not data_file:
        print("❌ Error: No data file found. Start the logger to create one first!")
        return

    print(f"Processing data from '{data_file}' to create actogram...")
    try:
        df = pd.read_csv(data_file)
        
        if df.empty:
            print("❌ Error: The data file is empty.")
            return

        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        df['Event_Count'] = 1 
        df.set_index('Timestamp', inplace=True)
        binned_data = df['Event_Count'].resample(f'{BIN_MINUTES}min').sum().reset_index()
        
        binned_data['Date'] = binned_data['Timestamp'].dt.date
        binned_data['Time_of_Day'] = binned_data['Timestamp'].dt.hour + (binned_data['Timestamp'].dt.minute / 60.0)
        
        unique_dates = binned_data['Date'].unique()
        num_days = len(unique_dates)
        
        fig, axes = plt.subplots(nrows=num_days, ncols=1, figsize=(10, 1.2 * num_days), sharex=True)
        
        if num_days == 1:
            axes = [axes]
            
        fig.suptitle(f'FED3 Feeding Actogram\n{data_file}', fontsize=14, fontweight='bold', y=1.05)
        bar_width_hours = BIN_MINUTES / 60.0

        for ax, date in zip(axes, unique_dates):
            day_data = binned_data[binned_data['Date'] == date]
            ax.axvspan(0, LIGHT_START, color='lightgray', alpha=0.4, lw=0)
            ax.axvspan(LIGHT_START, DARK_START, color='lemonchiffon', alpha=0.5, lw=0)
            ax.axvspan(DARK_START, 24, color='lightgray', alpha=0.4, lw=0)
            ax.bar(day_data['Time_of_Day'], day_data['Event_Count'], 
                   width=bar_width_hours, color='black', align='edge', edgecolor='none')
            ax.set_xlim(0, 24)
            ax.set_ylabel(date.strftime('%Y-%m-%d'), rotation=0, labelpad=40, ha='right', va='center', fontsize=9)
            ax.set_yticks([]) 
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_visible(False)
            ax.spines['bottom'].set_visible(False)

        axes[-1].set_xlabel('Time of Day (h)', fontsize=11, labelpad=10)
        axes[-1].set_xticks(range(0, 25, 2))
        axes[-1].spines['bottom'].set_visible(True) 
        plt.subplots_adjust(hspace=0.0)
        
        output_image = data_file.replace(".csv", "_actogram.png")
        plt.savefig(output_image, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close()
        print(f"🎉 Success! Actogram saved as '{output_image}'.")

    except Exception as e:
        print(f"❌ An error occurred while generating the actogram: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FED3 USB Data Monitor and Plotting Utility")
    parser.add_argument('--plot', action='store_true', help='Generate an actogram from the latest CSV data')
    args = parser.parse_args()

    if args.plot:
        generate_graph()
    else:
        log_live_data()