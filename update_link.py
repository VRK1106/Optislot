import os
import time
import requests
import subprocess
import re

# --- CONFIGURATION ---
SHORTIO_API_KEY = "sk_Niqi25E7KOnQVXIu"
DOMAIN_ID = "1589435"
DOMAIN_HOSTNAME = "smart-parking.short.gy"
LINK_PATH = "parking" # This will create/update smart-parking.short.gy/parking
DOCKER_SERVICE_NAME = "tunnel" # Name of the service in compose.yaml

def get_tunnel_url():
    """Scans docker logs for the Cloudflare Quick Tunnel URL."""
    print("Scanning for Cloudflare Tunnel URL...")
    start_time = time.time()
    
    # Retry for 60 seconds
    while time.time() - start_time < 60:
        try:
            # Run docker compose logs
            result = subprocess.run(["docker", "compose", "logs", DOCKER_SERVICE_NAME], capture_output=True, text=True)
            logs = result.stdout + result.stderr
            
            # Regex to find the URL
            matches = re.findall(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", logs)
            if matches:
                url = matches[-1] # Get the LAST match (most recent)
                print(f"Found Tunnel URL: {url}")
                return url
        except Exception as e:
            print(f"Error reading logs: {e}")
        
        time.sleep(2)
        print("Waiting for tunnel to initialize...")
        
    return None

def update_short_link(destination_url):
    """Updates (or creates) the Short.io link to point to the destination."""
    headers = {
        "Authorization": SHORTIO_API_KEY,
        "Content-Type": "application/json"
    }
    
    # 1. Try to find existing link by path (Direct Lookup)
    # This is more reliable than listing all links
    find_url = f"https://api.short.io/links/expand?domain={DOMAIN_HOSTNAME}&path={LINK_PATH}"
    print(f"DEBUG: Looking up link via {find_url}")
    
    link_id = None
    try:
        response = requests.get(find_url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            link_id = data.get('id')
            print(f"DEBUG: Found existing link ID: {link_id}")
        elif response.status_code == 404:
            print("DEBUG: Link not found (404). Will create new.")
        else:
            print(f"DEBUG: Lookup failed with status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"DEBUG: Exception during lookup: {e}")

    # 2. Update or Create
    if link_id:
        print(f"Link '/{LINK_PATH}' exists (ID: {link_id}). Updating...")
        update_payload = {
            "originalURL": destination_url
        }
        res = requests.post(f"https://api.short.io/links/{link_id}", json=update_payload, headers=headers)
    else:
        print(f"Link '/{LINK_PATH}' does not exist. Creating...")
        create_payload = {
            "domain": DOMAIN_HOSTNAME,
            "path": LINK_PATH,
            "originalURL": destination_url
        }
        res = requests.post("https://api.short.io/links", json=create_payload, headers=headers)
        
    if res.status_code in [200, 201]:
        print(f"SUCCESS! Static Link: https://{DOMAIN_HOSTNAME}/{LINK_PATH} -> {destination_url}")
    else:
        print(f"FAILED to update link: {res.text}")

if __name__ == "__main__":
    url = get_tunnel_url()
    if url:
        # Append /verify_ui to the base URL because that's where we want the QR to land (wait, no)
        # The QR generator appends /slot_id.
        # So the static link should redirect to the BASE of the tunnel?
        # If QR is: https://short.gy/parking/S001
        # Short.io can pass parameters?
        # NO. Short.io free plan generic link just redirects.
        # If we redirect `.../parking` -> `...trycloudflare.com/verify_ui`, then we can't append params easily unless Short.io passes path.
        # Short.io DOES pass parameters if configured, OR we can just rely on the user scanning `.../parking` and entering slot manual?
        # User wants "mapped to same tinyurl".
        # If we have 50 slots, we don't want 50 short links.
        # We need `smart-parking.short.gy/parking` -> `dynamic-url.com/verify_ui`.
        # AND we need `smart-parking.short.gy/parking?slot=S001` to work?
        # Standard Short.io behavior: Query parameters are passed through.
        # So `smart-parking.short.gy/parking?id=S001` -> `dynamic-url.com/verify_ui?id=S001`.
        # I need to adjust make_qrs.py to use query parameters instead of path parameters if Short.io doesn't support path forwarding on free.
        # Path forwarding is usually paid. Query params are usually free.
        # Let's target: `dynamic-url.com/verify_ui` as the destination.
        
        target = f"{url}/verify_ui"
        update_short_link(target)
    else:
        print("Could not find Cloudflare URL. Is `docker compose` running?")
