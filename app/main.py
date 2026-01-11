from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from typing import List

from app.config import load_tvs, save_tvs, CONFIG_PATH
from app.models import TV, WakeRequest
import app.wol as wol
import app.utils as utils

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
def toggle_power_tv(ip: str):
    """Toggle TV power state."""
    tvs = _get_tvs_dict()
    if ip not in tvs:
        raise HTTPException(status_code=404, detail="TV not found")

    token = tvs[ip].get("token")
    ws_port = tvs[ip].get("ws_port", 8002)

    try:
        success = utils.toggle_power(ip, ws_port, token)
        if success:
            # Clear power state cache to force refresh
            return {"ip": ip, "status": "toggled"}
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
