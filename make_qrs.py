import sqlite3
import qrcode
import os
import socket

# Import the registry client for permanent QR URLs
try:
    import registry_client
    REGISTRY_AVAILABLE = True
except ImportError:
    REGISTRY_AVAILABLE = False

DB_NAME = "parking.db"
QR_DIR = "qrs"

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def qrs_exist():
    """Check if QR codes already exist."""
    if not os.path.exists(QR_DIR):
        return False
    qr_files = [f for f in os.listdir(QR_DIR) if f.endswith('.png')]
    return len(qr_files) > 0

def get_registry_base_url():
    """Get the permanent QR base URL from registry."""
    if REGISTRY_AVAILABLE:
        try:
            return registry_client.get_qr_base_url()
        except Exception as e:
            print(f"[make_qrs] Registry URL error: {e}")
    return None

def get_tunnel_url():
    """Get the current tunnel URL from database (fallback)."""
    try:
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("SELECT public_url FROM network_config WHERE id=1")
            row = c.fetchone()
            if row and row[0]:
                return row[0]
    except Exception:
        pass
    return f"http://{get_local_ip()}:5000"

def generate_qrs(force=False, use_registry=True):
    """
    Generate QR codes for all parking slots.
    
    Args:
        force: If True, regenerate even if QRs exist
        use_registry: If True, use permanent registry URLs (recommended)
    """
    if not force and qrs_exist():
        print(f"[make_qrs] QR codes already exist in '{QR_DIR}'. Skipping.")
        return False
    
    # Create or clear directory
    if not os.path.exists(QR_DIR):
        os.makedirs(QR_DIR)
        print(f"[make_qrs] Created directory: {QR_DIR}")
    else:
        for f in os.listdir(QR_DIR):
            file_path = os.path.join(QR_DIR, f)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"[make_qrs] Error deleting {file_path}: {e}")
        print(f"[make_qrs] Cleared existing QR codes in {QR_DIR}")

    # Determine URL strategy
    registry_base = get_registry_base_url() if use_registry else None
    
    if registry_base:
        print(f"[make_qrs] Using PERMANENT Registry URLs: {registry_base}")
        url_mode = "registry"
    else:
        print(f"[make_qrs] Registry not available, using tunnel URLs (will need regeneration)")
        url_mode = "tunnel"

    # Get all slots from database
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT slot_id FROM slots")
        slots = c.fetchall()

    if not slots:
        print("[make_qrs] No slots found in database.")
        return False

    tunnel_url = get_tunnel_url()
    generated_count = 0

    # Generate QR for each slot
    for slot in slots:
        slot_id = slot[0]
        
        if url_mode == "registry":
            # Permanent URL via registry (recommended)
            url = f"{registry_base}/{slot_id}"
        else:
            # Direct tunnel URL (changes on restart)
            url = f"{tunnel_url}/verify_ui?slot_id={slot_id}"
        
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
        generated_count += 1

    print(f"[make_qrs] Generated {generated_count} QR codes in '{QR_DIR}' folder.")
    
    if url_mode == "registry":
        print(f"[make_qrs] ✓ All QR codes use PERMANENT registry URLs")
        print(f"[make_qrs] ✓ QR codes will NOT need regeneration after restart")
    else:
        print(f"[make_qrs] ⚠ QR codes use tunnel URLs (temporary)")
        
    return True

if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv or "-f" in sys.argv
    no_registry = "--no-registry" in sys.argv
    
    if force:
        print("[make_qrs] Force regeneration enabled.")
    
    generate_qrs(force=force, use_registry=not no_registry)
