import sqlite3
import datetime
import random
import cv2
import numpy as np
import easyocr
import re
import os
import threading
import time
import make_qrs # Import the QR generator module
from flask import Flask, render_template, request, jsonify, redirect, url_for, Response

# --- Project Imports ---
from agent import ParkingAgent
from network_manager import NetworkManager

# 1. Get the absolute path of the directory the script is running from
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# 2. Define the absolute path for the templates folder
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')

# 3. Pass the absolute path when creating the Flask app
app = Flask(__name__, template_folder=TEMPLATE_DIR)
DB_NAME = "parking.db"

# --- AGENT INITIALIZATION ---
# Initialize the Intelligent Agent
print("Initializing Real-Time Parking Agent...")
parking_agent = ParkingAgent() 
print("Agent Initialized.")

# --- SHARED CAMERA SINGLETON ---
# --- SHARED CAMERA SINGLETON ---
class SharedCamera:
    def __init__(self):
        # Try DSHOW first (Windows), then default
        print("Attempting to open camera with CAP_DSHOW...")
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
             print("CAP_DSHOW failed. Trying default backend...")
             self.cap = cv2.VideoCapture(0)
             
        self.lock = threading.Lock()
        self.last_frame = None
        self.is_running = True
        
        if not self.cap.isOpened():
            print("CRITICAL ERROR: Camera 0 could not be opened Check drivers/permissions.")
        else:
            print("Camera 0 Opened Successfully.")
        
        # Start background reading thread
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()

    def _update_loop(self):
        failure_count = 0
        while self.is_running:
            if self.cap.isOpened():
                success, frame = self.cap.read()
                if success:
                    with self.lock:
                        self.last_frame = frame.copy()
                    failure_count = 0
                else:
                    failure_count += 1
                    if failure_count > 10:
                        # print("Camera read failed repeatedly. Re-initializing...")
                        self.cap.release()
                        time.sleep(1)
                        self.cap = cv2.VideoCapture(0)
                        failure_count = 0
            else:
                time.sleep(1)
                self.cap = cv2.VideoCapture(0)
                
            time.sleep(0.01) # ~60 FPS cap

    def get_frame(self):
        with self.lock:
             if self.last_frame is not None:
                 return self.last_frame.copy()
        return None

    def __del__(self):
        self.is_running = False
        if self.cap and self.cap.isOpened():
            self.cap.release()

# Global Camera Instance
camera_system = None

def generate_frames():
    global camera_system
    if camera_system is None:
        camera_system = SharedCamera()
        
    while True:
        frame = camera_system.get_frame()
        if frame is None:
            # Send black frame if no camera
            blank = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(blank, "NO SIGNAL", (200, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            cv2.putText(blank, "Check Server Console", (180, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
            frame = blank
            
        try:
            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret:
                continue
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        except Exception as e:
            print(f"Frame encoding error: {e}")
            pass
        
        # Don't loop too fast if there's no camera
        if frame is None:
            time.sleep(0.5)

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        # Create slots table
        c.execute('''CREATE TABLE IF NOT EXISTS slots (
                        slot_id TEXT PRIMARY KEY,
                        size_type TEXT,
                        status TEXT DEFAULT 'free',
                        reg_num TEXT,
                        entry_time TEXT,
                        is_verified INTEGER DEFAULT 0
                    )''')
        # Create logs table for analytics
        c.execute('''CREATE TABLE IF NOT EXISTS logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        reg_num TEXT,
                        slot_id TEXT,
                        action TEXT,
                        timestamp TEXT
                    )''')
        # Create FASTag map table
        c.execute('''CREATE TABLE IF NOT EXISTS fastag_map (
                        tag_id TEXT PRIMARY KEY,
                        reg_num TEXT,
                        balance REAL
                    )''')
        
        # Initialize slots if empty
        c.execute("SELECT count(*) FROM slots")
        if c.fetchone()[0] == 0:
            # Generate 50 Slots Programmatically
            slots_data = []
            
            # 20 Small Slots (S001 - S020)
            slots_data.extend([(f'S{i:03d}', 'small') for i in range(1, 21)])
            
            # 20 Medium Slots (M001 - M020)
            slots_data.extend([(f'M{i:03d}', 'medium') for i in range(1, 21)])
            
            # 10 Large Slots (L001 - L010)
            slots_data.extend([(f'L{i:03d}', 'large') for i in range(1, 11)])

            c.executemany("INSERT INTO slots (slot_id, size_type) VALUES (?, ?)", slots_data)
            print("Initialized 50 Slots (20 Small, 20 Medium, 10 Large).")

        # Initialize FASTag data if empty
        c.execute("SELECT count(*) FROM fastag_map")
        if c.fetchone()[0] == 0:
            fastag_data = [
                ('TAG001', 'MH02AB1234', 500.0),
                ('TAG002', 'DL01XY9876', 250.0),
                ('TAG003', 'KA05ZZ5555', 1000.0)
            ]
            c.executemany("INSERT INTO fastag_map (tag_id, reg_num, balance) VALUES (?, ?, ?)", fastag_data)
            print("Initialized sample FASTag data.")


# --- Routes Refactored to use Agent ---

@app.route('/')
def index():
    return redirect(url_for('slots_dashboard'))

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/slots')
def slots_dashboard():
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM slots ORDER BY slot_id")
        slots = c.fetchall()
        
        # Calculate stats
        total = len(slots)
        occupied = sum(1 for s in slots if s['status'] == 'occupied')
        utilization = round((occupied / total) * 100, 1) if total > 0 else 0
        
    return render_template('index_sensor.html', utilization=utilization)

@app.route('/dashboard')
def dashboard_view():
    return render_template('dashboard.html')

@app.route('/status')
def allotment_status():
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM slots ORDER BY slot_id")
        slots = c.fetchall()
    return render_template('status.html', slots=slots)

@app.route('/entry', methods=['POST'])
def entry():
    try:
        data = request.json
        
        # 1. PERCEIVE: Agent receives data
        percepts = {
            'reg_num': data.get('reg_num'),
            'vehicle_size': data.get('vehicle_size', 'medium')
        }
        
        # 2. DECIDE: Agent makes a decision
        actions = parking_agent.decide(percepts)
        
        # 3. ACT: System executes Agent's chosen action
        response = None
        for action in actions:
            result = parking_agent.act(action)
            
            if action['type'] == 'GRANT_ACCESS':
                response = jsonify({"message": "Entry successful", "assigned_slot": result['assigned_slot'], "size": percepts['vehicle_size']})
            elif action['type'] == 'DENY_ACCESS':
                return jsonify({"error": result['message']}), 400
                
        if response:
            return response
        else:
            return jsonify({"error": "No action taken by Agent"}), 400

    except Exception as e:
        print(f"ENTRY ERROR: {e}")
        return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500

@app.route('/exit', methods=['POST'])
def exit_vehicle():
    # Currently simplest implementation - direct DB update. 
    # Can be moved to Agent.act('RELEASE_SLOT') later.
    try:
        data = request.json
        reg_num = data.get('reg_num')
        if not reg_num: return jsonify({"error": "Registration number required"}), 400
            
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("SELECT slot_id, entry_time FROM slots WHERE reg_num = ?", (reg_num,))
            row = c.fetchone()
            if not row: return jsonify({"error": "Vehicle not found"}), 404
            slot_id, entry_time = row
            
            duration_sec = 0
            if entry_time:
                entry_dt = datetime.datetime.fromisoformat(entry_time)
                duration_sec = (datetime.datetime.now() - entry_dt).total_seconds()
            
            c.execute("UPDATE slots SET status = 'free', reg_num = NULL, entry_time = NULL, is_verified = 0 WHERE slot_id = ?", (slot_id,))
            conn.commit()
            
        return jsonify({"message": "Exit successful", "freed_slot": slot_id, "duration_seconds": int(duration_sec)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/reset', methods=['POST'])
def reset_parking():
    try:
        # Directly create the action for the agent
        action = {'type': 'RESET_ALL'}
        
        # Agent acts on the command
        result = parking_agent.act(action)
        
        if result and result.get('status') == 'success':
             return jsonify(result)
        else:
             return jsonify({"error": "Reset failed", "details": result.get('message', '')}), 500

    except Exception as e:
        print(f"RESET ERROR: {e}")
        return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500

@app.route('/anpr', methods=['POST'])
def anpr():
    print("ANPR Request Received (Agent Perception)")
    try:
        global camera_system
        if camera_system is None:
             camera_system = SharedCamera()
             
        # Capture input (Use SHARED CAMERA resource)
        frame = camera_system.get_frame()
        
        if frame is None:
            return jsonify({"error": "Failed to capture image (Camera busy or off)"}), 500
            
        # 1. PERCEIVE: Send Image to Agent
        perception_result = parking_agent.perceive('image', frame)
        
        if 'error' in perception_result:
            return jsonify(perception_result), 400
            
        return jsonify(perception_result)

    except Exception as e:
        print(f"ANPR CRASH: {e}")
        return jsonify({"error": f"Internal Error: {str(e)}"}), 500

@app.route('/verify_ui')
@app.route('/verify_ui/<slot_id>')
def verify_ui(slot_id=None):
    if not slot_id:
        slot_id = request.args.get('slot_id')
    return render_template('verify.html', slot_id=slot_id)

@app.route('/process_verification', methods=['POST'])
def process_verification():
    # Verification is effectively a sensor check confirming location
    reg_num = request.form.get('reg_num')
    slot_id = request.form.get('slot_id')
    
    # Process via direct DB for now, but conceptually this is Agent matching 
    # expected state (Assigned Slot) vs Perceived State (QR Scan Location)
    reg_num = reg_num.strip().upper().replace(" ", "")
    
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT slot_id FROM slots WHERE reg_num = ?", (reg_num,))
        assigned_row = c.fetchone()
        
        if not assigned_row:
             return jsonify({"success": False, "message": "Vehicle not found."})
             
        assigned_slot = assigned_row[0]
        if assigned_slot != slot_id:
            # WRONG SLOT - Misuse Detected
            # UPDATE DB IMMEDIATELY to trigger Server Alert
            # Save reg_num so we know WHO caused it
            c.execute("UPDATE slots SET status = 'misuse', reg_num = ? WHERE slot_id = ?", (reg_num, slot_id))
            conn.commit()
            
            return jsonify({
                "success": False, 
                "status": "misuse",
                "assigned_slot": assigned_slot,
                "current_slot": slot_id,
                "message": f"Vehicle Assigned to {assigned_slot} but detected at {slot_id}."
            })
            
        c.execute("UPDATE slots SET is_verified = 1, status = 'occupied' WHERE slot_id = ?", (slot_id,))
        conn.commit()
        return jsonify({"success": True, "status": "verified", "message": "Verified!"})

@app.route('/resolve_misuse', methods=['POST'])
def resolve_misuse():
    try:
        data = request.json
        slot_id = data.get('slot_id') # The WRONG slot being used
        reg_num = data.get('reg_num')
        decision = data.get('decision') # 'accept' or 'reject'
        
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            
            # Find the ORIGINALLY assigned slot
            c.execute("SELECT slot_id FROM slots WHERE reg_num = ?", (reg_num,))
            row = c.fetchone()
            # If not found, that's okay, maybe cleared already
            assigned_slot = row[0] if row else None
            
            if decision == 'accept':
                # 1. Clear the Old Slot(s) - Wipe ALL instances of this car
                c.execute("UPDATE slots SET status = 'free', reg_num = NULL, entry_time = NULL, is_verified = 0 WHERE reg_num = ?", (reg_num,))
                
                # 2. Occupy the New Slot
                c.execute("UPDATE slots SET status = 'occupied', reg_num = ?, entry_time = ?, is_verified = 1 WHERE slot_id = ?", 
                          (reg_num, datetime.datetime.now().isoformat(), slot_id))
                msg = f"Re-assigned to {slot_id}"
                
            elif decision == 'resolved':
                # Vehicle moved away. Slot is free.
                c.execute("UPDATE slots SET status = 'free', reg_num = NULL, entry_time = NULL, is_verified = 0 WHERE slot_id = ?", (slot_id,))
                msg = "Incident Resolved. Slot Freed."

            else: # reject
                # Mark current slot as REJECTED so mobile can detect and show message
                c.execute("UPDATE slots SET status = 'rejected', reg_num = ?, is_verified = 0 WHERE slot_id = ?", (reg_num, slot_id))
                msg = "Access Rejected - Vehicle must move to assigned slot"
                
            conn.commit()
            return jsonify({"success": True, "message": msg})
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/nfc_scan', methods=['POST'])
def nfc_scan():
    data = request.json
    tag_id = data.get('tag_id')
    
    # 1. PERCEIVE: NFC Tap
    # 2. DECIDE: Agent checks balance/auth
    # For now, simplistic agent logic integration:
    
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT reg_num, balance FROM fastag_map WHERE tag_id = ?", (tag_id,))
        row = c.fetchone()
        if row:
            return jsonify({"status": "success", "reg_num": row[0], "balance": row[1]})
        return jsonify({"error": "Unknown Tag"}), 404

@app.route('/get_sensors', methods=['GET'])
def get_sensors():
    # Polling the Agent's state or Database
    # Here we can return database-driven alerts
    alerts = []
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT slot_id, reg_num FROM slots WHERE status = 'misuse'")
        for r in c.fetchall():
             alerts.append({"slot_id": r[0], "reg_num": r[1]})
             
    return jsonify({"alerts": alerts})

@app.route('/api/slots', methods=['GET'])
def api_slots():
    """
    Returns full slot list for the frontend dashboard.
    """
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM slots ORDER BY slot_id")
        rows = c.fetchall()
        
        # Convert to list of dicts
        slots = [dict(row) for row in rows]
        
    return jsonify(slots)

@app.route('/api/slot_status/<slot_id>', methods=['GET'])
def get_slot_status(slot_id):
    """
    Lightweight endpoint for mobile polling during verification.
    """
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT status, reg_num FROM slots WHERE slot_id = ?", (slot_id,))
        row = c.fetchone()
        if row:
            return jsonify({"status": row[0], "reg_num": row[1]})
        return jsonify({"error": "Slot not found"}), 404


# --- STARTUP ORCHESTRATION ---
if __name__ == '__main__':
    # 1. Initialize Database
    init_db()
    
    # 2. Network Auto-Configuration
    # This detects Local IP and Public Tunnel URL
    print("Configuring Network...")
    local_ip, public_url = NetworkManager.initialize()
    print(f"Network Configured. Local: {local_ip}, Public: {public_url}")
    
    # 3. Generate QR Codes (ONLY if they don't exist)
    print("Checking QR Codes...")
    qr_generated = make_qrs.generate_qrs(force=False)
    
    if not qr_generated and make_qrs.qrs_exist():
        print("[INFO] Existing QR codes found.")
    
    # Display current access URLs prominently
    print("\n" + "="*60)
    print("  SMART PARKING SYSTEM - ACCESS URLs")
    print("="*60)
    print(f"  Local Network:  http://{local_ip}:5000")
    print(f"  External URL:   {public_url}")
    print(f"  QR Codes:       {public_url}/verify_ui?slot_id=<slot_id>")
    print("="*60 + "\n")
    
    # Pre-warm camera system (Runs in separate thread)
    camera_system = SharedCamera()
    
    # 5. Start Server
    # Threaded=True allow for concurrent requests (video feed + api)
    # use_reloader=False prevents the app from starting twice in debug mode
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True, use_reloader=False)