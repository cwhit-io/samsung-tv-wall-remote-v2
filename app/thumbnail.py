import requests
import json

# CONFIGURATION
IP = "10.10.97.83"
PORT = "8080"
LAYER_INDEX = 1  # Which layer are you monitoring? (1 for Layer 1)

def get_active_clip_thumbnail():
    base_url = f"http://{IP}:{PORT}/api/v1"
    
    # STEP 1: Get Layer Info to find the Active Clip
    print(f"Checking Layer {LAYER_INDEX}...")
    try:
        layer_response = requests.get(f"{base_url}/composition/layers/{LAYER_INDEX}")
        layer_response.raise_for_status()
        layer_data = layer_response.json()
    except Exception as e:
        print(f"Failed to get layer: {e}")
        return

    # STEP 2: Find the Connected Clip ID
    active_clip_id = None
    
    # Iterate through clips in the layer to find the one that is "Connected"
    # Note: The API structure for clips usually contains a "connected" state
    for clip in layer_data.get('clips', []):
        # Different versions handle "connected" differently. 
        # We check for the specific enum or boolean usually found in 'connected'
        # In the raw JSON, look for "connected": "Connected" or similar.
        
        # A safer fallback is checking if the clip has a transport that is running
        # But let's assume standard API structure:
        connected_state = clip.get('connected', {}).get('value')
        
        # '2' usually means Connected/Playing in Resolume's internal logic, 
        # or sometimes it returns the string "Connected"
        if connected_state == "Connected" or connected_state == 2:
            active_clip_id = clip.get('id')
            name = clip.get('name', {}).get('value', 'Unknown')
            print(f"Found Active Clip: {name} (ID: {active_clip_id})")
            break
    
    if not active_clip_id:
        print("No clip is currently playing on this layer.")
        return

    # STEP 3: Get the Thumbnail for that Clip ID
    print(f"Downloading thumbnail for Clip {active_clip_id}...")
    thumb_url = f"{base_url}/composition/clips/by-id/{active_clip_id}/thumbnail"
    
    try:
        thumb_response = requests.get(thumb_url)
        if thumb_response.status_code == 200:
            with open(f"live_output_layer_{LAYER_INDEX}.jpg", "wb") as f:
                f.write(thumb_response.content)
            print("Success! Saved as live_output_layer_1.jpg")
        else:
            print(f"Error fetching thumbnail: {thumb_response.status_code}")
    except Exception as e:
        print(f"Failed to download thumbnail: {e}")

if __name__ == "__main__":
    get_active_clip_thumbnail()
