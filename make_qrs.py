import sqlite3
import qrcode
import os
import socket

DB_NAME = "parking.db"
QR_DIR = "qrs"

def get_local_ip():
    try:
        # Connect to an external server (doesn't actually send data) to get the local IP used for routing
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def generate_qrs():
    if not os.path.exists(QR_DIR):
        os.makedirs(QR_DIR)
        print(f"Created directory: {QR_DIR}")
    else:
        # Clear existing QRs
        for f in os.listdir(QR_DIR):
            file_path = os.path.join(QR_DIR, f)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")
        print(f"Cleared existing QR codes in {QR_DIR}")

    # Priority 1: Fetch Dynamic URL from Database (NetworkManager)
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("SELECT public_url FROM network_config WHERE id=1")
        row = c.fetchone()
        if row and row[0]:
            base_url = f"{row[0]}/verify_ui"
            print(f"Using Dynamic Network URL: {base_url}")
        else:
            base_url = "http://127.0.0.1:5000/verify_ui"
            print("Warning: No network config found. Using Localhost.")
    except Exception as e:
        base_url = "http://127.0.0.1:5000/verify_ui"
        print(f"Error reading network config: {e}")
    finally:
        conn.close()
    
    print(f"Generating QR codes pointing to: {base_url}?slot_id=<slot_id>")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT slot_id FROM slots")
    slots = c.fetchall()
    conn.close()

    if not slots:
        print("No slots found in database. Please run the main app first to initialize the DB.")
        return


    for slot in slots:
        slot_id = slot[0]
        # Unique ID removed to keep QRs static and printable
        
        # NOTE: Short.io converts `.../parking?slot=S001` -> `DestinationURL?slot=S001`
        # We need the destination endpoint to handle `?slot=S001` OR we maintain `.../slot_id` path structure.
        # Since path forwarding might not work on free, we'll use Query Param `slot_id`.
        url = f"{base_url}?slot_id={slot_id}"
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        file_path = os.path.join(QR_DIR, f"{slot_id}.png")
        img.save(file_path)
        print(f"Generated QR for {slot_id}: {file_path}")

    print(f"\nSuccessfully generated {len(slots)} QR codes in '{QR_DIR}' folder.")

def generate_custom_qr(url, filename):
    """Generate a QR code for the given URL and save as filename in QR_DIR."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    file_path = os.path.join(QR_DIR, filename)
    img.save(file_path)
    print(f"Generated custom QR for {url}: {file_path}")

if __name__ == "__main__":
    generate_qrs()
    # Custom link for main dashboard
    generate_custom_qr("https://smart-parking.short.gy/parking", "custom_link.png")
