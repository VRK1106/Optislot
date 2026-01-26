"""
Registry Client for Smart Parking System

This module handles communication with the FastAPI Dynamic Registry.
It registers the local system with its current URL so QR codes can redirect properly.
"""

import os
import uuid
import sqlite3
import requests
from dotenv import load_dotenv

load_dotenv()

# Configuration
DB_NAME = "parking.db"
REGISTRY_URL = os.getenv("REGISTRY_URL", "http://localhost:8000")
REGISTRY_API_KEY = os.getenv("REGISTRY_API_KEY", "dev-key-change-in-production")
UNIT_NAME = os.getenv("UNIT_NAME", "Smart Parking Unit")


def get_or_create_unit_id():
    """
    Get the unique unit ID from the database, or create a new one.
    This ID is the 'metadata unique ID' that identifies this parking unit.
    """
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        
        # Create table if not exists
        c.execute('''
            CREATE TABLE IF NOT EXISTS registry_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                unit_id TEXT NOT NULL,
                created_at TEXT
            )
        ''')
        
        # Try to get existing unit ID
        c.execute("SELECT unit_id FROM registry_config WHERE id = 1")
        row = c.fetchone()
        
        if row:
            return row[0]
        
        # Generate new UUID
        new_unit_id = str(uuid.uuid4())
        
        # Store it
        c.execute("""
            INSERT INTO registry_config (id, unit_id, created_at) 
            VALUES (1, ?, datetime('now'))
        """, (new_unit_id,))
        conn.commit()
        
        print(f"[Registry] Generated new Unit ID: {new_unit_id}")
        return new_unit_id


def register_with_registry(current_url):
    """
    Register this unit with the cloud registry.
    Called on system startup after the tunnel URL is obtained.
    
    Args:
        current_url: The current public URL (e.g., Cloudflare tunnel URL)
    
    Returns:
        dict with success status and QR base URL, or None on failure
    """
    unit_id = get_or_create_unit_id()
    
    try:
        response = requests.post(
            f"{REGISTRY_URL}/register",
            params={"api_key": REGISTRY_API_KEY},
            json={
                "unit_id": unit_id,
                "current_url": current_url,
                "unit_name": UNIT_NAME
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"[Registry] Registered successfully!")
            print(f"[Registry] QR Base URL: {data.get('qr_base_url')}")
            
            # Store the QR base URL in database
            _store_qr_base_url(data.get('qr_base_url'))
            
            return data
        else:
            print(f"[Registry] Registration failed: {response.status_code}")
            print(f"[Registry] Response: {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"[Registry] Connection error: {e}")
        return None


def _store_qr_base_url(qr_base_url):
    """Store the QR base URL in the database for make_qrs to use."""
    if not qr_base_url:
        return
        
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS registry_urls (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                qr_base_url TEXT,
                last_updated TEXT
            )
        """)
        c.execute("DELETE FROM registry_urls")
        c.execute("""
            INSERT INTO registry_urls (id, qr_base_url, last_updated) 
            VALUES (1, ?, datetime('now'))
        """, (qr_base_url,))
        conn.commit()


def get_qr_base_url():
    """
    Get the base URL for QR codes from the database.
    This is the registry URL that redirects to the current live session.
    """
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        try:
            c.execute("SELECT qr_base_url FROM registry_urls WHERE id = 1")
            row = c.fetchone()
            if row and row[0]:
                return row[0]
        except sqlite3.OperationalError:
            pass
    
    # Fallback: construct from unit ID
    unit_id = get_or_create_unit_id()
    return f"{REGISTRY_URL}/r/{unit_id}"


def get_slot_qr_url(slot_id):
    """
    Get the permanent QR URL for a specific slot.
    
    Args:
        slot_id: The slot identifier (e.g., 'S001', 'M005')
    
    Returns:
        The permanent URL that QR codes should point to
    """
    base_url = get_qr_base_url()
    return f"{base_url}/{slot_id}"


def check_registry_health():
    """Check if the registry server is reachable."""
    try:
        response = requests.get(f"{REGISTRY_URL}/", timeout=5)
        return response.status_code == 200
    except:
        return False


# --- CLI for testing ---
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        
        if cmd == "--check":
            print(f"Registry URL: {REGISTRY_URL}")
            if check_registry_health():
                print("✓ Registry is reachable")
            else:
                print("✗ Registry is not reachable")
        
        elif cmd == "--register":
            if len(sys.argv) > 2:
                url = sys.argv[2]
            else:
                url = "http://localhost:5000"
            
            result = register_with_registry(url)
            if result:
                print(f"✓ Registered: {result}")
            else:
                print("✗ Registration failed")
        
        elif cmd == "--unit-id":
            print(f"Unit ID: {get_or_create_unit_id()}")
        
        elif cmd == "--qr-url":
            if len(sys.argv) > 2:
                slot_id = sys.argv[2]
                print(f"QR URL for {slot_id}: {get_slot_qr_url(slot_id)}")
            else:
                print(f"QR Base URL: {get_qr_base_url()}")
        
        else:
            print("Unknown command")
    else:
        print("Usage:")
        print("  python registry_client.py --check         # Check registry health")
        print("  python registry_client.py --register URL  # Register with URL")
        print("  python registry_client.py --unit-id       # Show unit ID")
        print("  python registry_client.py --qr-url [slot] # Show QR URL")
