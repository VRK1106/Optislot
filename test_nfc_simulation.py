import requests
import sqlite3
import json
import time
from threading import Thread
from parking_proto import app, init_db

# Setup
DB_NAME = "parking.db"
BASE_URL = "http://127.0.0.1:5000"

def run_server():
    app.run(port=5000)

def test_fastag_flow():
    # Ensure DB is initialized
    init_db()
    
    # Check DB directly
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT count(*) FROM fastag_map")
        count = c.fetchone()[0]
        print(f"FASTag Map Count: {count}")
        assert count > 0, "FASTag map should not be empty"

    # Test API
    # We need the server running, but for this simple test we can use Flask's test client
    # or just assume the user will run it. 
    # Actually, let's use Flask's test client to avoid threading complexity.
    
    with app.test_client() as client:
        # Test Valid Tag
        response = client.post('/nfc_scan', json={"tag_id": "TAG001"})
        print(f"Scan Response: {response.json}")
        assert response.status_code == 200
        assert response.json['reg_num'] == "MH02AB1234"
        assert response.json['status'] == "success"
        
        # Test Invalid Tag
        response = client.post('/nfc_scan', json={"tag_id": "INVALID_TAG"})
        assert response.status_code == 404
        
        print("FASTag API Verification Passed!")

if __name__ == "__main__":
    try:
        test_fastag_flow()
    except Exception as e:
        print(f"Verification Failed: {e}")
        exit(1)
