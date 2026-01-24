
import socket
import subprocess
import time
import re
import sqlite3
import os
import requests

DB_NAME = "parking.db"
DOCKER_SERVICE_NAME = "tunnel" # Adjust if your service name in compose.yaml is different

class NetworkManager:
    @staticmethod
    def get_local_ip():
        """
        Determines the local LAN IP address.
        """
        try:
            # Connect to an external server (doesn't actually send data) to get the routing IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    @staticmethod
    def get_public_url():
        """
        Scans Docker logs for the Cloudflare Quick Tunnel URL.
        Retries for up to 30 seconds.
        """
        print("[NetworkManager] Scanning for Cloudflare Tunnel URL...")
        start_time = time.time()
        
        while time.time() - start_time < 30:
            try:
                # Run docker compose logs
                # Note: This assumes 'docker' and 'compose' are available in the env
                result = subprocess.run(["docker", "compose", "logs", DOCKER_SERVICE_NAME], capture_output=True, text=True)
                logs = result.stdout + result.stderr
                
                # Regex to find the URL (trycloudflare.com)
                matches = re.findall(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", logs)
                if matches:
                    url = matches[-1] # Get the most recent one
                    print(f"[NetworkManager] Found Tunnel URL: {url}")
                    return url
            except Exception as e:
                print(f"[NetworkManager] Error reading logs (simulating local fallback): {e}")
                # For development without Docker, fallback to None or Localhost
                pass
            
            time.sleep(2)
            
        print("[NetworkManager] Cloudflare URL not found. Using Fallback.")
        return None

    @staticmethod
    def update_db(local_ip, public_url):
        """
        Stores the network config in the database.
        """
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            # Create table if not exists
            c.execute('''CREATE TABLE IF NOT EXISTS network_config (
                            id INTEGER PRIMARY KEY CHECK (id = 1),
                            local_ip TEXT,
                            public_url TEXT,
                            last_updated TIMESTAMP
                        )''')
            
            # Upsert (Insert or Replace)
            # SQLite specific syntax for single row config
            c.execute("DELETE FROM network_config") # Clear old
            c.execute("INSERT INTO network_config (id, local_ip, public_url, last_updated) VALUES (1, ?, ?, CURRENT_TIMESTAMP)", 
                      (local_ip, public_url))
            conn.commit()
        print(f"[NetworkManager] Network Config Saved: IP={local_ip}, URL={public_url}")

    @staticmethod
    def initialize():
        local_ip = NetworkManager.get_local_ip()
        
        # 1. Start Tunnel Infrastructure
        print("[NetworkManager] Starting Cloudflare Tunnel via Docker...")
        try:
            # We use 'up -d' to ensure it's running detached
            subprocess.run(["docker", "compose", "up", "-d", "tunnel"], check=True)
            # Give it a moment to initialize
            time.sleep(3)
        except subprocess.CalledProcessError as e:
            print(f"[NetworkManager] Failed to start tunnel: {e}")

        # 2. Extract URL
        public_url = NetworkManager.get_public_url()
        
        # Fallback if no public URL (e.g. running locally without tunnel)
        if not public_url:
            print("[NetworkManager] Warning: No public tunnel found. QRs will be local-only.")
            public_url = f"http://{local_ip}:5000"
            
        NetworkManager.update_db(local_ip, public_url)
        return local_ip, public_url

if __name__ == "__main__":
    # Test run
    NetworkManager.initialize()
