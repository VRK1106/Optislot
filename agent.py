
import sqlite3
import datetime
import cv2
import numpy as np
import easyocr
import re
import os

# Define the Database Name
DB_NAME = "parking.db"

class ParkingAgent:
    """
    ParkingAgent: A Real-Time Intelligent Agent.
    
    Architecture:
    1. Percepts: Receives data from the Environment (Camera, Sensors, NFC).
    2. State: Maintains an internal model of the Parking Lot (Slots, Vehicles).
    3. Rules/Logic: Decides on actions based on Percepts + State.
    4. Actions: Effect changes on the Environment (Open Gate, Update DB, Alert).
    """
    
    def __init__(self, use_gpu=False):
        self.name = "SmartParkingAgent_V1"
        self.state = {
            "slots": [],
            "current_vehicle": None,
            "alerts": []
        }
        
        # Initialize Internal Models (The "Brain")
        print(f"[{self.name}] Initializing Perception Module...")
        self.ocr_reader = easyocr.Reader(['en'], gpu=use_gpu)
        print(f"[{self.name}] Perception Module Loaded.")
        
    def perceive(self, percept_type, data):
        """
        The Sensory Input mechanism.
        
        Args:
            percept_type (str): 'image', 'nfc', 'sensor_update'
            data: The raw data input.
            
        Returns:
            processed_info: Structured data derived from the percept.
        """
        timestamp = datetime.datetime.now()
        # print(f"[{self.name}] Perceiving {percept_type} at {timestamp}")
        
        if percept_type == 'image':
            return self._process_visual_input(data)
        elif percept_type == 'nfc':
            return self._process_nfc_input(data)
        elif percept_type == 'sensor_update':
            return self._update_internal_sensor_model(data)
            
        return None

    def run_pipeline(self, percept_type, data):
        """
        Efficiency Pipeline:
        1. Perceive (Data -> Info)
        2. Decide (Info -> Action)
        3. Act (Action -> Result)
        """
        # Step 1: Perception
        percepts = self.perceive(percept_type, data)
        
        # Step 2: Decision
        actions = self.decide(percepts)
        
        # Step 3: Action Execution
        results = []
        for action in actions:
            result = self.act(action)
            results.append(result)
            
        return results

    def decide(self, current_percepts):
        """
        The Reasoning mechanism. Decides what to do based on percepts.
        """
        actions = []
        if not current_percepts:
            return actions

        # Rule 0: Admin Reset
        if current_percepts.get('command') == 'RESET':
            return [{'type': 'RESET_ALL'}]
        
        # Rule 1: Visual Entry Request
        if 'reg_num' in current_percepts:
            reg_num = current_percepts['reg_num']
            # Decision Logic: Check if authorized or new entry
            action = self._decide_entry_logic(reg_num)
            actions.append(action)
            
        # Rule 2: NFC Entry Request
        if 'tag_id' in current_percepts:
            tag_id = current_percepts['tag_id']
            action = self._decide_nfc_logic(tag_id)
            actions.append(action)
            
        return actions

    def act(self, action):
        """
        The Actuator mechanism. Executes the chosen action.
        """
        if not action:
            return None
            
        action_type = action.get('type')
        print(f"[{self.name}] Executing Action: {action_type}")
        
        if action_type == 'GRANT_ACCESS':
            return self._act_grant_access(action['data'])
        elif action_type == 'DENY_ACCESS':
            return {'status': 'error', 'message': action['reason']}
        elif action_type == 'RESERVE_SLOT':
             return self._act_reserve_slot(action['data'])
        elif action_type == 'RELEASE_SLOT':
             return self._act_release_slot(action['data'])
        elif action_type == 'RESET_ALL':
            return self._act_reset_all()
             
        return {'status': 'unknown_action'}

    # --- Internal Reasoning Methods (The "Mind") ---
    
    def _process_visual_input(self, image):
        """
        Uses Computer Vision (OCR & QR) to extract meaning from the image.
        """
        # 1. Try QR Code Detection First (Readability & Speed Priority)
        try:
            detector = cv2.QRCodeDetector()
            data, bbox, _ = detector.detectAndDecode(image)
            
            if data:
                print(f"[{self.name}] QR Code Detected: {data}")
                # Map mechanism: Treat QR data as 'reg_num' so the Frontend (which expects reg_num) displays it.
                return {'qr_data': data, 'reg_num': data, 'confidence': 'high', 'type': 'qr'}
        except Exception as e:
            print(f"QR Detection Failure: {e}")

        # 2. Fallback to OCR if no QR or QR failed
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # Advanced Filtering
        bfilter = cv2.bilateralFilter(gray, 11, 17, 17) 
        thresh = cv2.adaptiveThreshold(bfilter, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        
        # OCR Reading
        result = self.ocr_reader.readtext(thresh, allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
        
        detected_text = ""
        # Sort by confidence
        result.sort(key=lambda x: x[2], reverse=True)
        
        for (bbox, text, prob) in result:
            clean = ''.join(e for e in text if e.isalnum()).upper()
            if len(clean) >= 6:
                detected_text = clean
                break
                
        # Error Correction Heuristics
        if detected_text:
            detected_text = self._correct_ocr_errors(detected_text)
            return {'reg_num': detected_text, 'confidence': 'high'}
            
        return {'error': 'No text detected'}

    def _correct_ocr_errors(self, text):
        # ... (Include the heuristic logic from the original script) ...
        if text.startswith("IND") and len(text) > 10: text = text[3:]
        
        chars = list(text)
        letter_map = {'0': 'O', '1': 'I', '2': 'Z', '5': 'S', '8': 'B', '4': 'A', '6': 'G'}
        number_map = {'O': '0', 'Q': '0', 'I': '1', 'Z': '2', 'S': '5', 'B': '8', 'A': '4', 'G': '6', 'T': '1'}
        
        if len(chars) == 10:
            if chars[0] in letter_map: chars[0] = letter_map[chars[0]]
            if chars[1] in letter_map: chars[1] = letter_map[chars[1]]
            if chars[2] in number_map: chars[2] = number_map[chars[2]]
            if chars[3] in number_map: chars[3] = number_map[chars[3]]
            if chars[4] in letter_map: chars[4] = letter_map[chars[4]]
            if chars[5] in letter_map: chars[5] = letter_map[chars[5]]
            for i in range(6, 10):
                if chars[i] in number_map: chars[i] = number_map[chars[i]]
        return "".join(chars)

    def _decide_entry_logic(self, reg_num):
        """
        Decides whether to let a car in based on current DB state.
        """
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("SELECT slot_id, status FROM slots WHERE reg_num = ?", (reg_num,))
            existing = c.fetchone()
            
            if existing:
                if existing[1] == 'reserved':
                    return {'type': 'GRANT_ACCESS', 'data': {'reg_num': reg_num, 'slot_id': existing[0], 'is_reservation': True}}
                else:
                    return {'type': 'DENY_ACCESS', 'reason': 'Vehicle already parked'}
            
            # Find new slot logic
            slot_id = self._find_best_slot_logic('medium') # Default to medium for camera
            if slot_id:
                return {'type': 'GRANT_ACCESS', 'data': {'reg_num': reg_num, 'slot_id': slot_id, 'is_reservation': False}}
            else:
                 return {'type': 'DENY_ACCESS', 'reason': 'Parking Full'}

    def _find_best_slot_logic(self, size):
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            search_order = ['medium', 'large'] if size == 'medium' else ['small', 'medium', 'large']
            for check_size in search_order:
                c.execute("SELECT slot_id FROM slots WHERE size_type = ? AND status = 'free' ORDER BY slot_id ASC LIMIT 1", (check_size,))
                result = c.fetchone()
                if result: return result[0]
        return None

    def _act_grant_access(self, data):
        reg_num = data['reg_num']
        slot_id = data['slot_id']
        
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            # INTEGRITY FIX: Clear any previous slot for this vehicle to prevent duplicates
            c.execute("UPDATE slots SET status = 'free', reg_num = NULL, entry_time = NULL, is_verified = 0 WHERE reg_num = ?", (reg_num,))
            
            c.execute("UPDATE slots SET status = 'reserved', reg_num = ?, entry_time = ?, is_verified = 0 WHERE slot_id = ?", 
                      (reg_num, datetime.datetime.now().isoformat(), slot_id))
            conn.commit()
            
        self._log_action(reg_num, slot_id, "ENTRY")
        return {'status': 'success', 'assigned_slot': slot_id}
    
    def _act_reset_all(self):
        try:
            with sqlite3.connect(DB_NAME) as conn:
                c = conn.cursor()
                c.execute("UPDATE slots SET status = 'free', reg_num = NULL, entry_time = NULL, is_verified = 0")
                conn.commit()
            self._log_action("ADMIN", "ALL", "RESET")
            print(f"[{self.name}] All slots reset successfully.")
            return {'status': 'success', 'message': 'All slots have been reset.'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def _log_action(self, reg_num, slot_id, action):
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            timestamp = datetime.datetime.now().isoformat()
            c.execute("INSERT INTO logs (reg_num, slot_id, action, timestamp) VALUES (?, ?, ?, ?)", 
                      (reg_num, slot_id, action, timestamp))
            conn.commit()

