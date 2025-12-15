import sqlite3
import datetime
import random
import cv2
import numpy as np
import easyocr
import re
import make_qrs # Import the QR generator module
from flask import Flask, render_template, request, jsonify, redirect, url_for, Response
import os

# 1. Get the absolute path of the directory the script is running from
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# 2. Define the absolute path for the templates folder
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')

# 3. Pass the absolute path when creating the Flask app
app = Flask(__name__, template_folder=TEMPLATE_DIR)
DB_NAME = "parking.db"

# Initialize EasyOCR Reader (Load once)
print("Loading EasyOCR Model...")
MODEL_STORAGE_PATH = '/app/easyocr_models'
reader = easyocr.Reader(['en'], gpu=False, model_storage_directory=MODEL_STORAGE_PATH, user_network_directory='/app/temp_user_networks')
print("EasyOCR Model Loaded.")

# Global Camera Variable (Lazy Init)
camera = None

class MockCamera:
    def __init__(self):
        # Create a black image with text
        self.frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(self.frame, "NO CAMERA DETECTED", (100, 200), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(self.frame, "Running in Docker Mode", (120, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1)

    def read(self):
        # Simulate successful read
        return True, self.frame.copy()

    def release(self):
        pass

def get_camera():
    global camera
    if camera is None:
        try:
            # 1. Attempt to open physical camera
            # Note: CAP_DSHOW is Windows-specific. We remove it for Docker/Linux compatibility.
            temp_cam = cv2.VideoCapture(0)
            
            if temp_cam is None or not temp_cam.isOpened():
                raise Exception("Camera 0 not found")
                
            # Test reading a frame
            ret, _ = temp_cam.read()
            if not ret:
                raise Exception("Camera 0 opened but returned no frame")
                
            camera = temp_cam
            print("Physical Camera Initialized Successfully.")
            
        except Exception as e:
            print(f"CAMERA ERROR: {e}")
            print("Using Mock Camera Fallback.")
            camera = MockCamera()
            
    return camera

# Global Sensor Data Store (In-memory)
SENSOR_DATA = {
    "left": 0,
    "right": 0,
    "last_updated": None
}

def generate_frames():
    cam = get_camera()
    while True:
        success, frame = cam.read()
        if not success:
            break
        else:
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

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

def find_best_slot(size):
    """
    Finds the best available slot based on vehicle size using 'Best Fit' logic.
    Hierarchy:
    - Small Vehicle: Small -> Medium -> Large
    - Medium Vehicle: Medium -> Large
    - Large Vehicle: Large
    """
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        
        # Define search order based on vehicle size
        search_order = []
        if size == 'small':
            search_order = ['small', 'medium', 'large']
        elif size == 'medium':
            search_order = ['medium', 'large']
        elif size == 'large':
            search_order = ['large']
            
        for check_size in search_order:
            c.execute("SELECT slot_id FROM slots WHERE size_type = ? AND status = 'free' ORDER BY slot_id ASC LIMIT 1", (check_size,))
            result = c.fetchone()
            if result:
                return result[0]
                
        return None

def log_action(reg_num, slot_id, action):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        timestamp = datetime.datetime.now().isoformat()
        c.execute("INSERT INTO logs (reg_num, slot_id, action, timestamp) VALUES (?, ?, ?, ?)", 
                  (reg_num, slot_id, action, timestamp))
        conn.commit()

# --- Routes ---

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
        
    # --- CHANGED: Render index_sensor.html instead of index.html ---
    return render_template('index_sensor.html', utilization=utilization)

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
        reg_num = data.get('reg_num')
        size = data.get('vehicle_size', 'medium') # Default to medium if not provided
        
        if not reg_num:
            return jsonify({"error": "Registration number required"}), 400

        # Validate Format: TTNNTTNNNN (e.g., MH02AB1234)
        if not re.match(r"^[A-Z]{2}\d{2}[A-Z]{2}\d{4}$", reg_num):
            return jsonify({"error": "Invalid format. Use TTNNTTNNNN (e.g., MH02AB1234)"}), 400
        
        # Check if already parked
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("SELECT slot_id, status FROM slots WHERE reg_num = ?", (reg_num,))
            existing = c.fetchone()
            if existing:
                if existing[1] == 'reserved':
                    # Confirming a reservation
                    slot_id = existing[0]
                    c.execute("UPDATE slots SET status = 'occupied', entry_time = ?, is_verified = 0 WHERE slot_id = ?", 
                              (datetime.datetime.now().isoformat(), slot_id))
                    conn.commit()
                    log_action(reg_num, slot_id, "ENTRY (RESERVED)")
                    return jsonify({"message": "Reservation Confirmed. Entry successful", "assigned_slot": slot_id, "size": size})
                else:
                    return jsonify({"error": "Vehicle already parked"}), 400

        # Use manually selected size
        slot_id = find_best_slot(size)
        
        if not slot_id:
            return jsonify({"error": "No available slots for this vehicle size", "size_detected": size}), 404
        
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("UPDATE slots SET status = 'occupied', reg_num = ?, entry_time = ?, is_verified = 0 WHERE slot_id = ?", 
                      (reg_num, datetime.datetime.now().isoformat(), slot_id))
            conn.commit()
        
        log_action(reg_num, slot_id, "ENTRY")
        return jsonify({"message": "Entry successful", "assigned_slot": slot_id, "size": size})
    except Exception as e:
        print(f"ENTRY ERROR: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500

@app.route('/exit', methods=['POST'])
def exit_vehicle():
    try:
        data = request.json
        reg_num = data.get('reg_num')
        
        if not reg_num:
            return jsonify({"error": "Registration number required"}), 400
            
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("SELECT slot_id, entry_time FROM slots WHERE reg_num = ?", (reg_num,))
            row = c.fetchone()
            
            if not row:
                return jsonify({"error": "Vehicle not found"}), 404
                
            slot_id, entry_time = row
            
            # Calculate duration (mock)
            if entry_time:
                entry_dt = datetime.datetime.fromisoformat(entry_time)
                duration_sec = (datetime.datetime.now() - entry_dt).total_seconds()
            else:
                duration_sec = 0
            
            c.execute("UPDATE slots SET status = 'free', reg_num = NULL, entry_time = NULL, is_verified = 0 WHERE slot_id = ?", (slot_id,))
            conn.commit()
            
        log_action(reg_num, slot_id, "EXIT")
        return jsonify({"message": "Exit successful", "freed_slot": slot_id, "duration_seconds": int(duration_sec)})
    except Exception as e:
        print(f"EXIT ERROR: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500

@app.route('/reserve', methods=['POST'])
def reserve_slot():
    data = request.json
    reg_num = data.get('reg_num')
    size = data.get('vehicle_size', 'medium')
    
    if not reg_num:
        return jsonify({"error": "Registration number required"}), 400
        
    # Check if already parked or reserved
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT slot_id FROM slots WHERE reg_num = ?", (reg_num,))
        if c.fetchone():
            return jsonify({"error": "Vehicle already has a slot"}), 400

    slot_id = find_best_slot(size)
    if not slot_id:
        return jsonify({"error": "No available slots to reserve"}), 404
        
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("UPDATE slots SET status = 'reserved', reg_num = ? WHERE slot_id = ?", (reg_num, slot_id))
        conn.commit()
        
    log_action(reg_num, slot_id, "RESERVE")
    return jsonify({"message": "Slot Reserved Successfully", "reserved_slot": slot_id})

@app.route('/reset', methods=['POST'])
def reset_parking():
    try:
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("UPDATE slots SET status = 'free', reg_num = NULL, entry_time = NULL, is_verified = 0")
            conn.commit()
            
        log_action("ADMIN", "ALL", "RESET")
        return jsonify({"message": "All slots released successfully"})
    except Exception as e:
        print(f"RESET ERROR: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500

@app.route('/admin/update_url', methods=['POST'])
def update_url():
    """
    Dynamically update the SERVER_URL and regenerate QR codes.
    Useful for temporary tunneling (ngrok/cloudflare) without restarting.
    """
    try:
        new_url = request.json.get('server_url')
        if not new_url:
            return jsonify({"error": "URL is required"}), 400
            
        # Update Environment Variable (for this process)
        os.environ['SERVER_URL'] = new_url
        
        # Regenerate QR Codes
        print(f"Updating SERVER_URL to: {new_url}")
        print("Regenerating QR Codes...")
        make_qrs.generate_qrs()
        
        return jsonify({"message": f"URL Updated to {new_url}. QR Codes Regenerated."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/anpr', methods=['POST'])
def anpr():
    print("ANPR Request Received")
    try:
        # Capture frame from camera
        cam = get_camera()
        success, frame = cam.read()
        if not success:
            return jsonify({"error": "Failed to capture image from camera"}), 500
            
        img = frame
        print("Image captured successfully. Processing...")

        # 1. Preprocessing
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        bfilter = cv2.bilateralFilter(gray, 11, 17, 17) # Noise removal
        
        # Adaptive Thresholding for better contrast
        thresh = cv2.adaptiveThreshold(bfilter, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        edged = cv2.Canny(bfilter, 30, 200) # Edge detection

        # 2. Plate Localization
        cnts_result = cv2.findContours(edged.copy(), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        contours = cnts_result[0] if len(cnts_result) == 2 else cnts_result[1]
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]
        
        location = None
        for contour in contours:
            approx = cv2.approxPolyDP(contour, 10, True)
            
            # Check for rectangular shape (4 points)
            if len(approx) == 4:
                # Aspect Ratio Filter (Plates are wider than tall)
                (x, y, w, h) = cv2.boundingRect(approx)
                ar = w / float(h)
                if ar >= 2.0 and ar <= 5.0: # Typical license plate AR
                    location = approx
                    break
        
        if location is not None:
            mask = np.zeros(gray.shape, np.uint8)
            new_image = cv2.drawContours(mask, [location], 0, 255, -1)
            new_image = cv2.bitwise_and(img, img, mask=mask)
            (x,y) = np.where(mask==255)
            (x1, y1) = (np.min(x), np.min(y))
            (x2, y2) = (np.max(x), np.max(y))
            cropped_image = gray[x1:x2+1, y1:y2+1]
            
            # Resize for better OCR
            cropped_image = cv2.resize(cropped_image, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            
            # Use allowlist for alphanumeric only
            result = reader.readtext(cropped_image, allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
        else:
            # Fallback: Try OCR on the whole image with thresholding
            result = reader.readtext(thresh, allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
            
        print(f"OCR Result: {result}")
            
        if not result:
            return jsonify({"error": "No text detected"}), 400
            
        detected_text = ""
        # Sort results by confidence
        result.sort(key=lambda x: x[2], reverse=True)
        
        for (bbox, text, prob) in result:
            clean = ''.join(e for e in text if e.isalnum()).upper()
            if len(clean) >= 6: # Minimum length for a plate
                detected_text = clean
                break
        
        if not detected_text and len(result) > 0:
             detected_text = ''.join(e for e in result[0][1] if e.isalnum()).upper()

        def correct_ocr_errors(text):
            # Standard Indian Plate: TTNNTTNNNN (e.g., MH02AB1234)
            # Length usually 10, sometimes 9 or 11
            
            if text.startswith("IND") and len(text) > 10:
                text = text[3:]
            
            # Basic character replacements
            chars = list(text)
            
            # Mapping for letters (first 2 chars, middle 2 chars)
            letter_map = {'0': 'O', '1': 'I', '2': 'Z', '5': 'S', '8': 'B', '4': 'A', '6': 'G'}
            # Mapping for numbers (next 2 chars, last 4 chars)
            number_map = {'O': '0', 'Q': '0', 'I': '1', 'Z': '2', 'S': '5', 'B': '8', 'A': '4', 'G': '6', 'T': '1'}
            
            # Heuristic correction based on position (assuming 10 chars)
            if len(chars) == 10:
                # Pos 0,1: Letters
                if chars[0] in letter_map: chars[0] = letter_map[chars[0]]
                if chars[1] in letter_map: chars[1] = letter_map[chars[1]]
                
                # Pos 2,3: Numbers
                if chars[2] in number_map: chars[2] = number_map[chars[2]]
                if chars[3] in number_map: chars[3] = number_map[chars[3]]
                
                # Pos 4,5: Letters
                if chars[4] in letter_map: chars[4] = letter_map[chars[4]]
                if chars[5] in letter_map: chars[5] = letter_map[chars[5]]
                
                # Pos 6,7,8,9: Numbers
                for i in range(6, 10):
                    if chars[i] in number_map: chars[i] = number_map[chars[i]]
                    
            return "".join(chars)

        detected_text = correct_ocr_errors(detected_text)
        return jsonify({"reg_num": detected_text, "raw_output": str(result)})

    except Exception as e:
        print(f"ANPR CRASH: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Internal Error: {str(e)}"}), 500

@app.route('/verify_ui')
@app.route('/verify_ui/<slot_id>')
def verify_ui(slot_id=None):
    if not slot_id:
        slot_id = request.args.get('slot_id')
    
    if not slot_id:
        return "Error: No slot_id provided", 400
        
    return render_template('verify.html', slot_id=slot_id)

@app.route('/process_verification', methods=['POST'])
def process_verification():
    reg_num = request.form.get('reg_num')
    slot_id = request.form.get('slot_id')
    
    if not reg_num or not slot_id:
        return jsonify({"error": "Missing data"}), 400
        
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        
        # 1. Find the slot actually assigned to this vehicle
        c.execute("SELECT slot_id FROM slots WHERE reg_num = ?", (reg_num,))
        assigned_row = c.fetchone()
        
        if not assigned_row:
            return jsonify({"success": False, "message": "Vehicle not found in system. Please enter valid registration."})
            
        assigned_slot = assigned_row[0]
        
        # 2. Compare assigned slot with scanned slot
        if assigned_slot != slot_id:
            # --- WRONG PARKING TRIGGER ---
            # Mark the SCANNED slot as 'misuse' and log the offender
            c.execute("UPDATE slots SET status = 'misuse', reg_num = ?, is_verified = 0 WHERE slot_id = ?", (reg_num, slot_id))
            conn.commit()
            
            return jsonify({
                "success": False, 
                "alert": True,
                "message": f"⚠️ WRONG SLOT! You are assigned to {assigned_slot}. You have scanned {slot_id}. Please move immediately!",
                "redirect_slot": assigned_slot
            })
            
        # 3. Correct Slot
        c.execute("UPDATE slots SET is_verified = 1 WHERE slot_id = ?", (slot_id,))
        conn.commit()
        return jsonify({"success": True, "message": "Verification Successful! Slot Verified."})

@app.route('/nfc_scan', methods=['POST'])
def nfc_scan():
    data = request.json
    tag_id = data.get('tag_id')
    
    if not tag_id:
        return jsonify({"error": "Tag ID required"}), 400
        
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT reg_num, balance FROM fastag_map WHERE tag_id = ?", (tag_id,))
        row = c.fetchone()
        
        if row:
            reg_num, balance = row
            return jsonify({
                "status": "success",
                "tag_id": tag_id,
                "reg_num": reg_num,
                "balance": balance,
                "message": "FASTag Scanned Successfully"
            })
        else:
            return jsonify({"error": "Unknown Tag ID"}), 404

@app.route('/update_sensors', methods=['POST'])
def update_sensors():
    """
    Endpoint for Raspberry Pi to send sensor data.
    Expected JSON: {"left": 50, "right": 50}
    """
    global SENSOR_DATA
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400
        
    SENSOR_DATA["left"] = data.get("left", 0)
    SENSOR_DATA["right"] = data.get("right", 0)
    SENSOR_DATA["last_updated"] = datetime.datetime.now().isoformat()
    
    return jsonify({"message": "Sensor data updated", "data": SENSOR_DATA})

@app.route('/get_sensors', methods=['GET'])
def get_sensors():
    """
    Endpoint for Frontend to poll sensor data.
    Also checks for any 'misuse' slots to trigger dashboard alerts.
    """
    # Check for misuse
    alerts = []
    try:
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("SELECT slot_id, reg_num FROM slots WHERE status = 'misuse'")
            misuse_slots = c.fetchall()
            for slot in misuse_slots:
                alerts.append({"slot_id": slot[0], "reg_num": slot[1]})
    except Exception as e:
        print(f"Error checking alerts: {e}")

    response_data = SENSOR_DATA.copy()
    response_data["alerts"] = alerts
    return jsonify(response_data)

@app.route('/surveillance_check', methods=['GET'])
def surveillance():
    """
    Simulates a surveillance check. 
    In a real system, this would compare camera feed vs DB.
    Here, we just return current status and maybe simulate a mismatch.
    """
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT slot_id, status, reg_num FROM slots")
        slots = c.fetchall()
        
    # Simulate a random anomaly
    alerts = []
    if random.random() < 0.1: # 10% chance of anomaly
        alerts.append({"slot": "S005", "issue": "Occupied but no entry log"})
        
    return jsonify({"status": "active", "alerts": alerts, "checked_slots": len(slots)})

if __name__ == '__main__':
    init_db()
    print("Generating new QR codes...")
    make_qrs.generate_qrs() # Generate QRs on startup
    # Run on 0.0.0.0 to be accessible, debug=True for dev
    app.run(host='0.0.0.0', port=5000, debug=True, threaded =True)