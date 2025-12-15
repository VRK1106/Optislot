import RPi.GPIO as GPIO
import time
import requests
import json

# --- Configuration ---
SERVER_URL = "http://<YOUR_LAPTOP_IP>:5000/update_sensors"  # Replace with your laptop's IP address
POLL_INTERVAL = 1.0  # Seconds between checks

# GPIO Pins (BCM Mode)
TRIG_LEFT = 23
ECHO_LEFT = 24
TRIG_RIGHT = 27
ECHO_RIGHT = 22

def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(TRIG_LEFT, GPIO.OUT)
    GPIO.setup(ECHO_LEFT, GPIO.IN)
    GPIO.setup(TRIG_RIGHT, GPIO.OUT)
    GPIO.setup(ECHO_RIGHT, GPIO.IN)
    
    # Ensure triggers are low
    GPIO.output(TRIG_LEFT, False)
    GPIO.output(TRIG_RIGHT, False)
    time.sleep(2)
    print("Sensors Initialized")

def get_distance(trig_pin, echo_pin):
    # Send 10us pulse
    GPIO.output(trig_pin, True)
    time.sleep(0.00001)
    GPIO.output(trig_pin, False)
    
    pulse_start = time.time()
    pulse_end = time.time()
    
    # Wait for Echo to go HIGH
    timeout = time.time() + 0.04 # 40ms timeout (approx 6m)
    while GPIO.input(echo_pin) == 0:
        pulse_start = time.time()
        if pulse_start > timeout:
            return 0
            
    # Wait for Echo to go LOW
    while GPIO.input(echo_pin) == 1:
        pulse_end = time.time()
        if pulse_end > timeout:
            return 0
            
    pulse_duration = pulse_end - pulse_start
    distance = pulse_duration * 17150  # Speed of sound (34300 cm/s) / 2
    return round(distance, 2)

def main():
    setup_gpio()
    try:
        while True:
            dist_left = get_distance(TRIG_LEFT, ECHO_LEFT)
            time.sleep(0.05) # Small delay between sensors to avoid interference
            dist_right = get_distance(TRIG_RIGHT, ECHO_RIGHT)
            
            payload = {
                "left": dist_left,
                "right": dist_right
            }
            
            print(f"Sending Data: Left={dist_left}cm, Right={dist_right}cm")
            
            try:
                response = requests.post(SERVER_URL, json=payload, timeout=2)
                if response.status_code == 200:
                    print("Server updated successfully.")
                else:
                    print(f"Server error: {response.status_code}")
            except requests.exceptions.RequestException as e:
                print(f"Connection failed: {e}")
                
            time.sleep(POLL_INTERVAL)
            
    except KeyboardInterrupt:
        print("Stopping...")
        GPIO.cleanup()

if __name__ == "__main__":
    main()
