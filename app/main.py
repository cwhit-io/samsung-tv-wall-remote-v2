from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import List
import asyncio
from concurrent.futures import ThreadPoolExecutor
import requests
import socket
import select
import time
import subprocess
import platform

from app.config import load_tvs, save_tvs, CONFIG_PATH
from app.models import TV, WakeRequest
import app.wol as wol
import app.utils as utils
import app.thumbnail as thumbnail

app = FastAPI(title="TV WOL Service")

# CORS - allow local dev React server origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8002", "http://127.0.0.1:8002"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files served from root
static_dir = Path(__file__).resolve().parents[0] / "static"

from fastapi import APIRouter
import json

router = APIRouter(prefix="/api")

# Resolume configuration
RESOLUME_IP = "10.10.97.83"
RESOLUME_PORT = "8080"
RESOLUME_BASE_URL = f"http://{RESOLUME_IP}:{RESOLUME_PORT}/api/v1"


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
def tvs_status(force: bool = False):
    """Return list of TVs with their online status (ping), websocket port check, and token verification.
    
    Args:
        force: If True, bypass cache and force fresh checks
    """
    tvs = _get_tvs_dict()
    result = []
    for ip, data in tvs.items():
        ping_online = utils.cached_ping_host(ip, force=force)
        # default websocket port is 8002, allow override from config per-TV with key 'ws_port'
        ws_port = data.get("ws_port", 8002)
        ws_online = utils.cached_check_tcp_port(ip, ws_port, force=force)
        token = data.get("token")
        token_verified = utils.cached_check_websocket_endpoint(ip, ws_port, token, force=force)
        power_state = (
            utils.cached_get_power_state(ip, ws_port, token, force=force) if token_verified else None
        )
        
        # TV is considered "online" if either ping works OR websocket is accessible
        # (Samsung TVs sometimes don't respond to ping but are actually on)
        online = ping_online or ws_online
        
        result.append(
            {
                "ip": ip,
                "name": data.get("name"),
                "mac": data.get("mac"),
                "online": online,
                "ping_online": ping_online,
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


@router.post("/tvs/wake-all")
def wake_all_tvs(req: WakeRequest):
    """Send WOL magic packets to all TVs."""
    tvs = _get_tvs_dict()
    results = {
        "success": [],
        "failed": [],
        "skipped": []
    }
    
    for ip, tv_data in tvs.items():
        tv_name = tv_data.get("name", ip)
        mac = tv_data.get("mac")
        
        if not mac:
            results["skipped"].append({
                "ip": ip,
                "name": tv_name,
                "reason": "No MAC address configured"
            })
            continue
        
        try:
            wol.send_magic_packet_unicast(mac, ip, req.port)
            results["success"].append({
                "ip": ip,
                "name": tv_name,
                "mac": mac
            })
        except Exception as e:
            results["failed"].append({
                "ip": ip,
                "name": tv_name,
                "error": str(e)
            })
    
    return {
        "total": len(tvs),
        "success_count": len(results["success"]),
        "failed_count": len(results["failed"]),
        "skipped_count": len(results["skipped"]),
        "port": req.port,
        "results": results
    }


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
        
        # Check if TV is online (ping OR websocket)
        ping_online = utils.cached_ping_host(ip, force=True)
        ws_online = utils.cached_check_tcp_port(ip, port, force=True)
        
        if not (ping_online or ws_online):
            return {
                "status": "skipped",
                "ip": ip,
                "name": tv_name,
                "reason": "TV offline"
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
        # Get Layer Info to find the Active Clip
        layer_response = requests.get(f"{RESOLUME_BASE_URL}/composition/layers/{layer}", timeout=5)
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
        thumb_url = f"{RESOLUME_BASE_URL}/composition/clips/by-id/{active_clip_id}/thumbnail"
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
        response = requests.get(f"{RESOLUME_BASE_URL}/composition/layers", timeout=5)
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


@router.get("/resolume/columns")
def get_resolume_columns(layer: int = 1):
    """Get list of all columns from Resolume composition.

    Note: Resolume's per-column 'connected' state is best reflected by looking
    at the clips on a specific layer. This endpoint therefore accepts a
    `layer` query param and derives `connected` from that layer's clips.
    """
    try:
        # Get composition to find column count
        comp_response = requests.get(f"{RESOLUME_BASE_URL}/composition", timeout=5)
        comp_response.raise_for_status()
        comp_data = comp_response.json()
        
        # Try to get columns from the composition structure
        # Columns might be in the composition object or we need to iterate through layers
        columns = []
        
        # Determine number of columns by checking the requested layer
        layer_response = requests.get(f"{RESOLUME_BASE_URL}/composition/layers/{layer}", timeout=5)
        if layer_response.status_code == 200:
            layer_data = layer_response.json()
            clips = layer_data.get('clips', [])
            
            # Get info for each column by index
            for i in range(len(clips)):
                column_index = i + 1
                clip = clips[i]
                connected = clip.get('connected', {}).get('value', False)
                try:
                    # Prefer the column header name from Resolume's columns API
                    col_response = requests.get(f"{RESOLUME_BASE_URL}/composition/columns/{column_index}", timeout=2)
                    if col_response.status_code == 200:
                        col_data = col_response.json()
                        name = col_data.get('name', {}).get('value', f'Column {column_index}')
                    else:
                        name = clip.get('name', {}).get('value', f'Column {column_index}')
                except Exception:
                    name = clip.get('name', {}).get('value', f'Column {column_index}')

                columns.append({
                    'index': column_index,
                    'name': name,
                    'connected': connected,
                })
        
        return {'columns': columns}
        
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Resolume server timeout")
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="Cannot connect to Resolume server")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get columns: {str(e)}")


@router.post("/resolume/column/{column_index}/connect")
def trigger_resolume_column(column_index: int, layer: int = 1):
    """Trigger (fire) a specific column in Resolume for a given layer.

    Resolume's clip connect endpoints behave like triggers and are reliably
    activated via an *empty POST* (no JSON body). We therefore map a
    (layer, column) selection to the corresponding clip ID and trigger it.

    Column index is 1-based (Column 1, Column 2, etc.)
    """
    try:
        layer_response = requests.get(f"{RESOLUME_BASE_URL}/composition/layers/{layer}", timeout=5)
        if layer_response.status_code != 200:
            raise HTTPException(status_code=404, detail=f"Resolume layer {layer} not found")

        layer_data = layer_response.json()
        clips = layer_data.get('clips', [])
        clip_idx = column_index - 1
        if clip_idx < 0 or clip_idx >= len(clips):
            raise HTTPException(status_code=404, detail=f"No clip at column {column_index} on layer {layer}")

        clip_id = clips[clip_idx].get('id')
        if not clip_id:
            raise HTTPException(status_code=500, detail=f"Clip at column {column_index} on layer {layer} has no id")

        # Trigger the clip (empty POST)
        response = requests.post(
            f"{RESOLUME_BASE_URL}/composition/clips/by-id/{clip_id}/connect",
            timeout=5
        )

        if response.status_code not in [200, 204]:
            response.raise_for_status()

        return {
            "status": "success",
            "column": column_index,
            "layer": layer,
            "clip_id": clip_id,
        }
        
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Resolume server timeout")
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="Cannot connect to Resolume server")
    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Resolume API error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger column: {str(e)}")



@router.post("/resolume/layer/{layer_index}/connect")
def connect_resolume_layer(layer_index: int):
    """Connect (activate) a specific layer in Resolume."""
    try:
        # Set the layer's connect value to true
        response = requests.post(
            f"{RESOLUME_BASE_URL}/composition/layers/{layer_index}/connect",
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
        response = requests.get(f"{RESOLUME_BASE_URL}/composition/layers/{layer_index}", timeout=5)
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
        # Resolume clip connect behaves like a trigger: use an empty POST.
        response = requests.post(
            f"{RESOLUME_BASE_URL}/composition/clips/by-id/{clip_id}/connect",
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


@router.get("/config/tvs")
def api_get_tvs():
    """Return parsed TV configuration (validates JSON server-side).

    This is safer for the frontend than serving the raw file directly because
    it returns a descriptive 5xx error when the JSON is invalid.
    """
    if not CONFIG_PATH.exists():
        raise HTTPException(status_code=404, detail="Config file not found")
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Invalid JSON in config: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load config: {e}")


# Debug helper endpoints: ping, port check, SSDP discovery, and wake-and-wait
@router.get("/debug/ping")
def debug_ping(ip: str, force: bool = False):
    """Return whether the host responds to ping (uses cached_ping_host)."""
    print(f"[debug] ping requested for ip={ip} force={force}")
    if not ip:
        raise HTTPException(status_code=400, detail="Missing ip parameter")
    try:
        ok = utils.cached_ping_host(ip, force=force)
        return {"ok": bool(ok)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/port")
def debug_port(ip: str, port: int = 8002, force: bool = False):
    """Check whether a TCP port is open on the host (uses cached_check_tcp_port)."""
    print(f"[debug] port check requested for ip={ip} port={port} force={force}")
    if not ip:
        raise HTTPException(status_code=400, detail="Missing ip parameter")
    try:
        ok = utils.cached_check_tcp_port(ip, port, force=force)
        return {"ok": bool(ok), "port": port}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/ssdp")
def debug_ssdp(ip: str | None = None, timeout: float = 2.0):
    """Perform an SSDP M-SEARCH and return received responses (basic implementation).

    If `ip` is provided, filter responses to those originating from that IP.
    """
    print(f"[debug] ssdp requested for ip={ip} timeout={timeout}")
    MCAST_GRP = ("239.255.255.250", 1900)

    msg = (
        "M-SEARCH * HTTP/1.1\r\n"
        f"HOST: {MCAST_GRP[0]}:{MCAST_GRP[1]}\r\n"
        "MAN: \"ssdp:discover\"\r\n"
        "MX: 1\r\n"
        "ST: ssdp:all\r\n"
        "\r\n"
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(timeout)

    results = []
    try:
        sock.sendto(msg.encode("utf-8"), MCAST_GRP)
        start = time.time()
        while True:
            try:
                data, addr = sock.recvfrom(2048)
            except socket.timeout:
                break
            text = data.decode("utf-8", errors="replace")
            # parse headers into a dict
            headers = {}
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            for line in lines[1:]:  # skip response/status line
                if ":" in line:
                    k, v = line.split(":", 1)
                    headers[k.strip().lower()] = v.strip()
            entry = {"from": addr[0], "raw": text, "headers": headers}
            results.append(entry)
            if time.time() - start > timeout:
                break
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SSDP discovery failed: {e}")
    finally:
        sock.close()

    if ip:
        filtered = [r for r in results if r.get("from") == ip]
        return {"results": filtered, "ok": len(filtered) > 0}
    return {"results": results, "ok": len(results) > 0}


@router.get("/debug/ping-raw")
def debug_ping_raw(ip: str, count: int = 3, timeout: int = 1):
    """Run the system ping command and return the raw output for diagnostics.

    Query params:
      - ip: target IP
      - count: number of pings to send
      - timeout: per-ping timeout in seconds
    """
    print(f"[debug] raw ping requested for ip={ip} count={count} timeout={timeout}")
    if not ip:
        raise HTTPException(status_code=400, detail="Missing ip parameter")

    system = platform.system().lower()
    if "windows" in system:
        cmd = ["ping", "-n", str(count), "-w", str(int(timeout * 1000)), ip]
    else:
        # linux / mac
        cmd = ["ping", "-c", str(count), "-W", str(int(timeout)), ip]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=max(5, count * (timeout + 1)))
        stdout = res.stdout.decode("utf-8", errors="replace")
        stderr = res.stderr.decode("utf-8", errors="replace")
        return {"rc": res.returncode, "stdout": stdout, "stderr": stderr}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Ping command timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ping failed: {e}")


from pydantic import BaseModel


class DebugWakeRequest(BaseModel):
    ip: str
    port: int = 9
    wait_seconds: int = 30


@router.post("/debug/wake-and-wait")
def debug_wake_and_wait(req: DebugWakeRequest):
    """Send a WOL magic packet (unicast) and wait for the host to respond to ping.

    Accepts JSON body: { ip, port=9, wait_seconds=30 }

    Returns: { sent: bool, became_online: bool, waited_seconds: n }
    """
    ip = req.ip
    port = req.port
    wait_seconds = req.wait_seconds

    if not ip:
        raise HTTPException(status_code=400, detail="Missing ip parameter")

    print(f"[debug] wake-and-wait called for ip={ip} port={port} wait_seconds={wait_seconds}")

    tvs = _get_tvs_dict()
    if ip not in tvs:
        raise HTTPException(status_code=404, detail="TV not found")

    mac = tvs[ip].get("mac")
    if not mac:
        raise HTTPException(status_code=400, detail="MAC address not configured for TV")

    try:
        wol.send_magic_packet_unicast(mac, ip, port)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"WOL failed to send: {e}")

    # Wait for ping to succeed up to wait_seconds
    start = time.time()
    became_online = False
    while time.time() - start < wait_seconds:
        if utils.cached_ping_host(ip, force=True):
            became_online = True
            break
        time.sleep(2)

    return {"sent": True, "became_online": became_online, "waited_seconds": int(time.time() - start)}

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
