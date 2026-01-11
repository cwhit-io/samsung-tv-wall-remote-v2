import requests
import json

# CONFIGURATION
IP = "10.10.97.83"
PORT = "8080"
LAYER_INDEX = 1  # Which layer are you monitoring?
BASE_URL = f"http://{IP}:{PORT}/api/v1"
OUTPUT_FILENAME = f"live_output_layer_{LAYER_INDEX}.jpg"

def download_image(url, description):
    """Helper to download and save an image."""
    try:
        print(f"Attempting to download {description}...")
        response = requests.get(url, timeout=2)
        if response.status_code == 200:
            with open(OUTPUT_FILENAME, "wb") as f:
                f.write(response.content)
            print(f"✅ Success! Saved {description} to {OUTPUT_FILENAME}")
            return True
        else:
            print(f"❌ Failed to download {description}. Status: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error downloading {description}: {e}")
        return False

def get_dummy_thumbnail():
    """Fallback: Gets the default dummy thumbnail."""
    print("⚠️ Triggering fallback to Dummy Thumbnail...")
    url = f"{BASE_URL}/composition/thumbnail/dummy"
    download_image(url, "Dummy Thumbnail")

def get_active_clip_thumbnail():
    # STEP 1: Get Layer Info
    print(f"Checking Layer {LAYER_INDEX}...")
    try:
        layer_url = f"{BASE_URL}/composition/layers/{LAYER_INDEX}"
        layer_response = requests.get(layer_url, timeout=2)
        
        if layer_response.status_code != 200:
            print(f"Layer endpoint returned {layer_response.status_code}")
            get_dummy_thumbnail()
            return

        layer_data = layer_response.json()
    except Exception as e:
        print(f"Failed to connect to Resolume: {e}")
        get_dummy_thumbnail()
        return

    # STEP 2: Find the Connected Clip ID
    active_clip_id = None
    
    for clip in layer_data.get('clips', []):
        # Check for "Connected" state (String 'Connected' or Enum 2)
        connected_state = clip.get('connected', {}).get('value')
        
        if connected_state == "Connected" or connected_state == 2:
            active_clip_id = clip.get('id')
            name = clip.get('name', {}).get('value', 'Unknown')
            print(f"Found Active Clip: {name} (ID: {active_clip_id})")
            break
    
    # FALLBACK: If no clip is playing
    if not active_clip_id:
        print("No clip is currently playing on this layer.")
        get_dummy_thumbnail()
        return

    # STEP 3: Get the Thumbnail for that Clip ID
    thumb_url = f"{BASE_URL}/composition/clips/by-id/{active_clip_id}/thumbnail"
    
    # Try to download specific clip; if fail, download dummy
    success = download_image(thumb_url, f"Clip {active_clip_id}")
    if not success:
        get_dummy_thumbnail()

if __name__ == "__main__":
    get_active_clip_thumbnail()
