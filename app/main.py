from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from typing import List
import asyncio
from concurrent.futures import ThreadPoolExecutor
import requests

from app.config import load_tvs, save_tvs, CONFIG_PATH
from app.models import TV, WakeRequest
import app.wol as wol
import app.utils as utils
import app.thumbnail as thumbnail

app = FastAPI(title="TV WOL Service")

# Static files served from root
static_dir = Path(__file__).resolve().parents[0] / "static"

from fastapi import APIRouter

router = APIRouter(prefix="/api")


def _get_tvs_dict():
    return load_tvs()


@router.get("/tvs", response_model=List[TV])
def list_tvs():
    tvs = _get_tvs_dict()
    result = []
    for ip, data in tvs.items():
        result.append(TV(ip=ip, **data))
    return result


@router.get("/tvs/status")
def tvs_status():
    """Return list of TVs with their online status (ping), websocket port check, and token verification."""
    tvs = _get_tvs_dict()
    result = []
    for ip, data in tvs.items():
        online = utils.cached_ping_host(ip)
        # default websocket port is 8002, allow override from config per-TV with key 'ws_port'
        ws_port = data.get("ws_port", 8002)
        ws_online = utils.cached_check_tcp_port(ip, ws_port)
        token = data.get("token")
        token_verified = utils.cached_check_websocket_endpoint(ip, ws_port, token)
        power_state = (
            utils.cached_get_power_state(ip, ws_port, token) if token_verified else None
        )
        result.append(
            {
                "ip": ip,
                "name": data.get("name"),
                "mac": data.get("mac"),
                "online": online,
                "ws_online": ws_online,
                "token_verified": token_verified,
                "power_state": power_state,
            }
        )
    return result


@router.get("/tvs/{ip}", response_model=TV)
def get_tv(ip: str):
    tvs = _get_tvs_dict()
    if ip not in tvs:
        raise HTTPException(status_code=404, detail="TV not found")
    return TV(ip=ip, **tvs[ip])


@router.post("/tvs/{ip}/wake")
def wake_tv(ip: str, req: WakeRequest):
    tvs = _get_tvs_dict()
    if ip not in tvs:
        raise HTTPException(status_code=404, detail="TV not found")
    mac = tvs[ip].get("mac")
    if not mac:
        raise HTTPException(status_code=400, detail="MAC address not known")
    try:
        wol.send_magic_packet_unicast(mac, ip, req.port)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"WOL failed: {e}")
    return {"ip": ip, "mac": mac, "port": req.port, "status": "sent"}


@router.post("/tvs/{ip}/power")
async def toggle_power_tv(ip: str):
    """Toggle TV power state. If TV is offline, sends WOL first."""
    tvs = _get_tvs_dict()
    if ip not in tvs:
        raise HTTPException(status_code=404, detail="TV not found")

    token = tvs[ip].get("token")
    ws_port = tvs[ip].get("ws_port", 8002)
    mac = tvs[ip].get("mac")
    
    # Check if TV is online
    is_online = utils.cached_ping_host(ip, force=True)
    wol_was_sent = False
    
    # If offline and we have a MAC address, send WOL first
    if not is_online and mac:
        try:
            wol.send_magic_packet_unicast(mac, ip, 9)
            wol_was_sent = True
            # Wait for TV to wake up (typically takes 3-5 seconds)
            await asyncio.sleep(5)
            # Force refresh ping cache to see if it's now online
            is_online = utils.cached_ping_host(ip, force=True)
        except Exception as e:
            # If WOL fails, we'll still try to toggle power in case it's actually on
            pass

    try:
        success = utils.toggle_power(ip, ws_port, token)
        if success:
            return {"ip": ip, "status": "toggled", "wol_sent": wol_was_sent}
        else:
            raise HTTPException(status_code=500, detail="Failed to toggle power")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Power toggle failed: {e}")


@router.get("/tvs/{ip}/ws-check")
def ws_check(ip: str, force: bool = False):
    """Check a list of websocket endpoints for a TV, using its configured token.

    Returns a list of endpoints attempted with boolean `ok` values.
    Accepts optional query param `force=true` to bypass cache.
    """
    tvs = _get_tvs_dict()
    if ip not in tvs:
        raise HTTPException(status_code=404, detail="TV not found")
    token = tvs[ip].get("token")
    # Candidate websocket ports to check (expandable)
    ports = [tvs[ip].get("ws_port", 8002)]
    results = []
    for p in ports:
        ok = utils.cached_check_websocket_endpoint(ip, p, token, force=force)
        url = f"ws://{ip}:{p}/?token={token}" if token else f"ws://{ip}:{p}/"
        results.append({"url": url, "ok": ok, "port": p})
    return results


@router.get("/tvs/{ip}/info")
def tv_info(ip: str, force: bool = False):
    """Query the TV for a more complete status using the TV websocket API (if available).

    Returns a dict with fields returned by the TV client or an error message.
    Accepts optional query param `force=true` to bypass cache.
    """
    tvs = _get_tvs_dict()
    if ip not in tvs:
        raise HTTPException(status_code=404, detail="TV not found")
    token = tvs[ip].get("token")
    port = tvs[ip].get("ws_port", 8002)
    try:
        info = utils.cached_query_tv_info(ip, port, token, force=force)
        return {"ok": True, "info": info}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/tvs/{ip}/token")
def request_new_token_endpoint(ip: str):
    """Request a new token from the TV by initiating pairing.

    This will trigger a pairing prompt on the TV that the user must accept.
    Returns the new token if pairing succeeds.
    """
    tvs = _get_tvs_dict()
    if ip not in tvs:
        raise HTTPException(status_code=404, detail="TV not found")

    port = tvs[ip].get("ws_port", 8002)
    app_name = "TVControlPanel"  # App name shown on TV

    # Pre-check: Ensure TV is reachable
    if not utils.cached_ping_host(ip):
        raise HTTPException(
            status_code=400,
            detail="TV is not responding to ping. Please ensure the TV is turned ON (not in standby mode) and connected to the network.",
        )

    if not utils.cached_check_tcp_port(ip, port):
        raise HTTPException(
            status_code=400,
            detail=f"TV WebSocket port {port} is not accessible. TV may be off, in standby mode, or WebSocket service not running.",
        )

    try:
        token = utils.request_new_token(ip, port, app_name)
        
        # Save the new token to the config file
        tvs[ip]["token"] = token
        save_tvs(tvs)
        
        return {"token": token, "message": "New token obtained and saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token request failed: {e}")


@router.post("/tvs/refresh-all-tokens")
def refresh_all_tokens():
    """Request new tokens from all TVs that are online and accessible.

    This will attempt to pair with all TVs in the configuration.
    Each TV will display a pairing prompt that must be accepted.
    Returns a summary of successful and failed token refreshes.
    """
    tvs = _get_tvs_dict()
    app_name = "TVControlPanel"
    
    results = {
        "success": [],
        "failed": [],
        "skipped": []
    }
    
    for ip, tv_data in tvs.items():
        port = tv_data.get("ws_port", 8002)
        tv_name = tv_data.get("name", ip)
        
        # Check if TV is online
        if not utils.cached_ping_host(ip):
            results["skipped"].append({
                "ip": ip,
                "name": tv_name,
                "reason": "TV not responding to ping"
            })
            continue
        
        if not utils.cached_check_tcp_port(ip, port):
            results["skipped"].append({
                "ip": ip,
                "name": tv_name,
                "reason": f"Port {port} not accessible"
            })
            continue
        
        # Try to get new token
        try:
            token = utils.request_new_token(ip, port, app_name)
            tvs[ip]["token"] = token
            results["success"].append({
                "ip": ip,
                "name": tv_name,
                "token": token
            })
        except Exception as e:
            results["failed"].append({
                "ip": ip,
                "name": tv_name,
                "error": str(e)
            })
    
    # Save all successful tokens
    if results["success"]:
        save_tvs(tvs)
    
    return {
        "total": len(tvs),
        "success_count": len(results["success"]),
        "failed_count": len(results["failed"]),
        "skipped_count": len(results["skipped"]),
        "results": results
    }


@router.post("/tvs/broadcast-key")
async def broadcast_key_to_all(request: dict):
    """Send a key command to all TVs in parallel.
    
    For power commands (KEY_POWER), sends WOL to offline TVs first.
    
    Request body should contain:
    {
        "key": "KEY_MUTE" // or any other Samsung TV key code
    }
    
    Returns a summary of successful and failed commands.
    """
    if "key" not in request:
        raise HTTPException(status_code=400, detail="Missing 'key' in request body")
    
    key = request["key"]
    tvs = _get_tvs_dict()
    
    results = {
        "success": [],
        "failed": [],
        "skipped": [],
        "wol_sent": []
    }
    
    # First pass: Send WOL to all offline TVs if it's a power command
    if key in ["KEY_POWER", "KEY_POWEROFF", "KEY_POWERON"]:
        for ip, tv_data in tvs.items():
            mac = tv_data.get("mac")
            if mac and not utils.cached_ping_host(ip, force=True):
                try:
                    wol.send_magic_packet_unicast(mac, ip, 9)
                    results["wol_sent"].append({
                        "ip": ip,
                        "name": tv_data.get("name", ip)
                    })
                except Exception:
                    pass
        
        # Wait for TVs to wake up if we sent any WOL packets
        if results["wol_sent"]:
            await asyncio.sleep(5)
    
    # Function to send key to a single TV
    def send_to_tv(ip: str, tv_data: dict):
        tv_name = tv_data.get("name", ip)
        port = tv_data.get("ws_port", 8002)
        token = tv_data.get("token")
        
        # Check if TV is online (force refresh to get latest status)
        if not utils.cached_ping_host(ip, force=True):
            return {
                "status": "skipped",
                "ip": ip,
                "name": tv_name,
                "reason": "TV offline"
            }
        
        # Skip if websocket port is not accessible
        if not utils.cached_check_tcp_port(ip, port, force=True):
            return {
                "status": "skipped",
                "ip": ip,
                "name": tv_name,
                "reason": f"WebSocket port {port} not accessible"
            }
        
        # Try to send the key
        try:
            utils.send_key_command(ip, key, port, token)
            return {
                "status": "success",
                "ip": ip,
                "name": tv_name,
                "key": key
            }
        except Exception as e:
            return {
                "status": "failed",
                "ip": ip,
                "name": tv_name,
                "error": str(e)
            }
    
    # Execute all commands in parallel using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=len(tvs)) as executor:
        # Submit all tasks
        futures = {
            executor.submit(send_to_tv, ip, tv_data): (ip, tv_data)
            for ip, tv_data in tvs.items()
        }
        
        # Collect results as they complete
        for future in futures:
            result = future.result()
            status = result.pop("status")
            if status == "success":
                results["success"].append(result)
            elif status == "failed":
                results["failed"].append(result)
            else:  # skipped
                results["skipped"].append(result)
    
    response = {
        "key": key,
        "total": len(tvs),
        "success_count": len(results["success"]),
        "failed_count": len(results["failed"]),
        "skipped_count": len(results["skipped"]),
        "results": results
    }
    
    # Add WOL info if any WOL packets were sent
    if results["wol_sent"]:
        response["wol_sent_count"] = len(results["wol_sent"])
        response["wol_sent"] = results["wol_sent"]
    
    return response


@router.post("/tvs/{ip}/send-key")
async def send_key_to_tv(ip: str, request: dict):
    """Send a key command to a specific TV.
    
    Request body should contain:
    {
        "key": "KEY_MUTE" // or any other Samsung TV key code
    }
    
    Returns confirmation of the command sent.
    """
    if "key" not in request:
        raise HTTPException(status_code=400, detail="Missing 'key' in request body")
    
    tvs = _get_tvs_dict()
    if ip not in tvs:
        raise HTTPException(status_code=404, detail="TV not found")
    
    key = request["key"]
    tv_data = tvs[ip]
    tv_name = tv_data.get("name", ip)
    port = tv_data.get("ws_port", 8002)
    token = tv_data.get("token")
    
    try:
        utils.send_key_command(ip, key, port, token)
        return {
            "ip": ip,
            "name": tv_name,
            "key": key,
            "status": "sent"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send key: {str(e)}")


@router.get("/thumbnail")
async def get_thumbnail(layer: int = 1):
    """Get the current thumbnail from Resolume and return as image.
    
    Query parameter:
        layer: Layer index to get thumbnail from (default: 1)
    """
    try:
        # Use the same config from thumbnail.py
        IP = "10.10.97.83"
        PORT = "8080"
        
        base_url = f"http://{IP}:{PORT}/api/v1"
        
        # Get Layer Info to find the Active Clip
        layer_response = requests.get(f"{base_url}/composition/layers/{layer}", timeout=5)
        layer_response.raise_for_status()
        layer_data = layer_response.json()
        
        # Find the Connected Clip ID
        active_clip_id = None
        for clip in layer_data.get('clips', []):
            connected_state = clip.get('connected', {}).get('value')
            if connected_state == "Connected" or connected_state == 2:
                active_clip_id = clip.get('id')
                break
        
        if not active_clip_id:
            # Return a 1x1 transparent pixel if no clip is active
            # This prevents frontend errors while showing no content
            transparent_pixel = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
            return Response(content=transparent_pixel, media_type="image/png")
        
        # Get the Thumbnail for that Clip ID
        thumb_url = f"{base_url}/composition/clips/by-id/{active_clip_id}/thumbnail"
        thumb_response = requests.get(thumb_url, timeout=5)
        thumb_response.raise_for_status()
        
        return Response(content=thumb_response.content, media_type="image/jpeg")
        
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Resolume server timeout")
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="Cannot connect to Resolume server")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch thumbnail: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/resolume/layers")
def get_resolume_layers():
    """Get list of all layers from Resolume."""
    try:
        IP = "10.10.97.83"
        PORT = "8080"
        base_url = f"http://{IP}:{PORT}/api/v1"
        
        response = requests.get(f"{base_url}/composition/layers", timeout=5)
        response.raise_for_status()
        
        layers_data = response.json()
        # Return simplified layer info
        layers = []
        for layer in layers_data:
            if isinstance(layer, dict):
                layers.append({
                    "id": layer.get("id"),
                    "name": layer.get("name", {}).get("value", "Unknown"),
                    "index": layer.get("index")
                })
        
        return {"layers": layers}
        
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Resolume server timeout")
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="Cannot connect to Resolume server")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get layers: {str(e)}")


@router.post("/resolume/layer/{layer_index}/connect")
def connect_resolume_layer(layer_index: int):
    """Connect (activate) a specific layer in Resolume."""
    try:
        IP = "10.10.97.83"
        PORT = "8080"
        base_url = f"http://{IP}:{PORT}/api/v1"
        
        # Set the layer's connect value to true
        response = requests.post(
            f"{base_url}/composition/layers/{layer_index}/connect",
            json={"value": True},
            timeout=5
        )
        response.raise_for_status()
        
        return {"status": "success", "layer": layer_index}
        
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Resolume server timeout")
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="Cannot connect to Resolume server")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect layer: {str(e)}")


@router.get("/resolume/layer/{layer_index}/clips")
def get_resolume_layer_clips(layer_index: int):
    """Get all clips for a specific layer."""
    try:
        IP = "10.10.97.83"
        PORT = "8080"
        base_url = f"http://{IP}:{PORT}/api/v1"
        
        response = requests.get(f"{base_url}/composition/layers/{layer_index}", timeout=5)
        response.raise_for_status()
        layer_data = response.json()
        
        clips = []
        for clip in layer_data.get('clips', []):
            if isinstance(clip, dict):
                clips.append({
                    "id": clip.get("id"),
                    "name": clip.get("name", {}).get("value", "Unknown"),
                    "connected": clip.get("connected", {}).get("value")
                })
        
        return {"layer": layer_index, "clips": clips}
        
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Resolume server timeout")
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="Cannot connect to Resolume server")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get clips: {str(e)}")


@router.post("/resolume/clip/{clip_id}/connect")
def connect_resolume_clip(clip_id: int):
    """Connect (trigger) a specific clip in Resolume."""
    try:
        IP = "10.10.97.83"
        PORT = "8080"
        base_url = f"http://{IP}:{PORT}/api/v1"
        
        # Trigger the clip by setting its connect value
        response = requests.post(
            f"{base_url}/composition/clips/by-id/{clip_id}/connect",
            json={"value": True},
            timeout=5
        )
        response.raise_for_status()
        
        return {"status": "success", "clip_id": clip_id}
        
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Resolume server timeout")
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="Cannot connect to Resolume server")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect clip: {str(e)}")


# Include API router under /api
app.include_router(router)


# Backwards-compatible legacy routes (mirror /tvs/* to /api/tvs/*)
@app.get("/tvs", response_model=List[TV])
def list_tvs_legacy():
    return list_tvs()


@app.get("/tvs/{ip}", response_model=TV)
def get_tv_legacy(ip: str):
    return get_tv(ip)


@app.get("/tvs/status")
def tvs_status_legacy():
    return tvs_status()


@app.post("/tvs/{ip}/wake")
def wake_tv_legacy(ip: str, req: WakeRequest):
    return wake_tv(ip, req)


# Mount static files under /static and serve from root via explicit handlers
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
def root():
    """Serve the main index/home page at root."""
    page = static_dir / "index.html"
    if not page.exists():
        # Fallback to status page if index doesn't exist
        page = static_dir / "status.html"
    if not page.exists():
        raise HTTPException(status_code=404, detail="Index page not found")
    return FileResponse(str(page))


@app.get("/status.html")
def status_page_direct():
    """Serve the status page directly."""
    page = static_dir / "status.html"
    if not page.exists():
        raise HTTPException(status_code=404, detail="Status page not found")
    return FileResponse(str(page))


@app.get("/config/tvs.json")
def serve_config():
    """Serve the config/tvs.json file at /config/tvs.json for the UI."""
    if CONFIG_PATH.exists():
        return FileResponse(str(CONFIG_PATH), media_type="application/json")
    raise HTTPException(status_code=404, detail="Config not found")


@app.get("/{file_path:path}")
def static_files(file_path: str):
    """Serve arbitrary static files from the static directory at root paths."""
    file = static_dir / file_path
    if file.exists() and file.is_file():
        return FileResponse(str(file))
    raise HTTPException(status_code=404, detail="File not found")


@app.get("/status")
def status_page():
    """Serve the status HTML page."""
    page = static_dir / "status.html"
    if not page.exists():
        raise HTTPException(status_code=404, detail="Status page not found")
    return FileResponse(str(page))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
