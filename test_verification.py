import unittest
import json
import os
import sys
from unittest.mock import MagicMock

# Mock easyocr and cv2
sys.modules['easyocr'] = MagicMock()
sys.modules['cv2'] = MagicMock()
sys.modules['imutils'] = MagicMock()

try:
    import parking_proto
    from parking_proto import app, init_db
except ImportError as e:
    print(f"Import failed: {e}")
    sys.exit(1)

class ParkingTestCase(unittest.TestCase):
    def setUp(self):
        # Use a test database
        self.test_db = "test_parking.db"
        parking_proto.DB_NAME = self.test_db
        
        # Remove existing test db
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
            
        # Initialize DB
        init_db()
        
        app.config['TESTING'] = True
        self.app = app.test_client()

    def tearDown(self):
        # Clean up
        if os.path.exists(self.test_db):
            try:
                os.remove(self.test_db)
            except PermissionError:
                pass # Might be locked, ignore for now

    def test_1_slots_exist(self):
        response = self.app.get('/slots')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Smart Parking Management System', response.data)
        # Check if slots are rendered (e.g., S001)
        self.assertIn(b'S001', response.data)

    def test_2_entry_small(self):
        response = self.app.post('/entry', json={'reg_num': 'DL01AB1234'})
        data = json.loads(response.data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['size'], 'small')
        self.assertTrue(data['assigned_slot'].startswith('S'))

    def test_3_entry_medium(self):
        response = self.app.post('/entry', json={'reg_num': 'MH02CD5678'})
        data = json.loads(response.data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['size'], 'medium')
        self.assertTrue(data['assigned_slot'].startswith('M'))

    def test_4_exit(self):
        # First enter
        self.app.post('/entry', json={'reg_num': 'DL01AB1234'})
        # Then exit
        response = self.app.post('/exit', json={'reg_num': 'DL01AB1234'})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('freed_slot', data)

if __name__ == '__main__':
    unittest.main()
