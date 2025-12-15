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

    # Use Local IP for development/local testing
    # local_ip = get_local_ip()
    # base_url = f"http://{local_ip}:5000/verify_ui"
    # print(f"Using Local IP: {base_url}")
    
    # Priority 1: Use Static Short.io Link (Best for Stable QRs)
    # The Cloudflare URL changes, but this link is updated by update_link.py
    base_url = "https://smart-parking.short.gy/parking"
    print(f"Using Static Short Link: {base_url}")

    # Legacy/Debug overrides (Commented out)
    # base_url = "https://your-ngrok-url.ngrok-free.dev/verify_ui"
    
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
