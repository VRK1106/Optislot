import json
import os
import sqlite3
from parking_proto_sensor import app, init_db, DB_NAME

def run_tests():
    print("Running manual tests...")
    app.config['TESTING'] = True
    
    with app.app_context():
        init_db()
        
    client = app.test_client()
    
    # 1. Reset
    print("\n[TEST] Reset Parking...")
    rv = client.post('/reset')
    print(f"Status: {rv.status_code}")
    print(f"Response: {rv.json}")
    if rv.status_code != 200:
        print("❌ RESET FAILED")
        return

    # 2. Entry
    print("\n[TEST] Vehicle Entry (MH02AB1234)...")
    entry_data = {"reg_num": "MH02AB1234", "vehicle_size": "medium"}
    rv = client.post('/entry', json=entry_data)
    print(f"Status: {rv.status_code}")
    print(f"Response: {rv.json}")
    
    if rv.status_code != 200:
        print("❌ ENTRY FAILED")
        return
    
    slot_id = rv.json.get('assigned_slot')
    print(f"✅ Assigned Slot: {slot_id}")

    # 3. Duplicate Entry
    print("\n[TEST] Duplicate Entry (MH02AB1234)...")
    rv = client.post('/entry', json=entry_data)
    print(f"Status: {rv.status_code}")
    print(f"Response: {rv.json}")
    if rv.status_code == 400:
        print("✅ Correctly rejected duplicate")
    else:
        print("❌ FAILED: Should have rejected duplicate")

    # 4. Exit
    print("\n[TEST] Vehicle Exit (MH02AB1234)...")
    exit_data = {"reg_num": "MH02AB1234"}
    rv = client.post('/exit', json=exit_data)
    print(f"Status: {rv.status_code}")
    print(f"Response: {rv.json}")
    
    if rv.status_code == 200 and rv.json.get('freed_slot') == slot_id:
        print("✅ EXIT SUCCESSFUL")
    else:
        print("❌ EXIT FAILED")

if __name__ == "__main__":
    try:
        run_tests()
    except Exception as e:
        print(f"Test Crashed: {e}")
        import traceback
        traceback.print_exc()
