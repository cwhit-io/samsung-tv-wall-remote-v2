from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import List
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
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
import app.keepalive as keepalive

app = FastAPI(title="TV WOL Service")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files served from root
static_dir = Path(__file__).resolve().parents[0] / "static"

from fastapi import APIRouter
import json

router = APIRouter(prefix="/api")

# NOTE: Legacy Resolume integration removed. The UI retains a header link
# to the Resolume web UI; all server-side Resolume endpoints and thumbnail
# fetching code were removed to simplify the service.

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

    # Worker to perform checks for a single TV. Use slightly shorter timeouts
    # to keep overall response latency low; results are cached by utils.
    def _check_one(ip: str, data: dict):
        ws_port = data.get("ws_port", 8002)
        token = data.get("token")
        try:
            ping_online = utils.cached_ping_host(ip, timeout=0.8, force=force)
            ws_online = utils.cached_check_tcp_port(ip, ws_port, timeout=0.8, force=force)
            token_verified = utils.cached_check_websocket_endpoint(ip, ws_port, token, timeout=0.8, force=force)
            power_state = (
                utils.cached_get_power_state(ip, ws_port, token, timeout=1.0, force=force) if token_verified else None
            )
        except Exception:
            ping_online = False
            ws_online = False
            token_verified = False
            power_state = None

        online = ping_online or ws_online
        return {
            "ip": ip,
            "name": data.get("name"),
            "mac": data.get("mac"),
            "online": online,
            "ping_online": ping_online,
            "ws_online": ws_online,
            "token_verified": token_verified,
            "power_state": power_state,
        }

    # Run checks in parallel so slow/unreachable TVs don't block the whole request.
    max_workers = min(20, max(4, len(tvs)))
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_check_one, ip, data): ip for ip, data in tvs.items()}
        for fut in as_completed(futures):
            try:
                result.append(fut.result())
            except Exception:
                # In case a future itself errors, include a minimal failed entry
                ip = futures.get(fut)
                data = tvs.get(ip, {})
                result.append({
                    "ip": ip,
                    "name": data.get("name"),
                    "mac": data.get("mac"),
                    "online": False,
                    "ping_online": False,
                    "ws_online": False,
                    "token_verified": False,
                    "power_state": None,
                })

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
    app_name = utils.APP_NAME  # Must match name used in SamsungTVWS commands

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
        utils.invalidate_token_cache(ip)
        
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
    app_name = utils.APP_NAME  # Must match name used in SamsungTVWS commands
    
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
            utils.invalidate_token_cache(ip)
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


# Resolume endpoints removed: legacy server-side connection and thumbnail
# handling were removed per request. The static UI still contains a header
# link pointing at the Resolume web UI; no server-side Resolume integration
# is present anymore.


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


# Start background keepalive task on startup and cancel on shutdown
@app.on_event("startup")
async def _start_keepalive():
    try:
        app.state.keepalive_task = asyncio.create_task(keepalive.keepalive_loop())
    except Exception:
        # ensure startup doesn't fail if keepalive has problems
        import traceback
        traceback.print_exc()


@app.on_event("shutdown")
async def _stop_keepalive():
    task = getattr(app.state, "keepalive_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


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


# Mount static assets (CSS, JS)
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/config/tvs.json")
def serve_config():
    """Serve the config/tvs.json file at /config/tvs.json for the UI."""
    if CONFIG_PATH.exists():
        return FileResponse(str(CONFIG_PATH), media_type="application/json")
    raise HTTPException(status_code=404, detail="Config not found")


@app.get("/")
def root():
    page = static_dir / "index.html"
    if not page.exists():
        raise HTTPException(status_code=404, detail="UI not found")
    return FileResponse(str(page))


@app.get("/status.html")
def status_page():
    page = static_dir / "status.html"
    if not page.exists():
        raise HTTPException(status_code=404, detail="Status page not found")
    return FileResponse(str(page))


@app.get("/debug.html")
def debug_page():
    page = static_dir / "debug.html"
    if not page.exists():
        raise HTTPException(status_code=404, detail="Debug page not found")
    return FileResponse(str(page))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8009, reload=True)
