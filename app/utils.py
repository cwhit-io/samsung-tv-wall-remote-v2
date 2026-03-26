import subprocess
import platform
import socket
from typing import Tuple
from time import time
import threading

# App name shown on Samsung TV pairing prompt.
# Must be identical everywhere: token acquisition AND command execution.
APP_NAME = "SamsungTVRemote"

# Simple in-memory TTL cache for expensive checks
_cache = {}
_cache_lock = threading.Lock()

DEFAULT_CACHE_TTL = {
    "ping": 5,  # seconds
    "tcp": 30,
    "token": 60,
    "info": 60,
}


def _cache_get(key):
    with _cache_lock:
        entry = _cache.get(key)
        if not entry:
            return None
        value, expires_at = entry
        if time() > expires_at:
            del _cache[key]
            return None
        return value


def _cache_set(key, value, ttl):
    with _cache_lock:
        _cache[key] = (value, time() + ttl)


def invalidate_token_cache(host: str) -> None:
    """Remove all cached token-verification results for a given host.

    Call this immediately after saving a new token so stale results don't mask
    the fresh token on the next verification check.
    """
    with _cache_lock:
        keys_to_delete = [k for k in _cache if k[0] == "token" and k[1] == host]
        for k in keys_to_delete:
            del _cache[k]


def ping_host(ip: str, timeout: float = 1.0) -> bool:
    """Ping an IP once. Returns True if host is reachable.

    Uses the system `ping` command for portability (no raw sockets required).
    """
    system = platform.system().lower()
    if "windows" in system:
        cmd = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), ip]
    else:
        # mac/linux
        cmd = ["ping", "-c", "1", "-W", str(int(timeout)), ip]

    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout + 0.5,
        )
        return res.returncode == 0
    except Exception:
        return False


def cached_ping_host(
    ip: str, timeout: float = 1.0, ttl: int | None = None, force: bool = False
) -> bool:
    """Cached wrapper around ping_host."""
    if ttl is None:
        ttl = DEFAULT_CACHE_TTL["ping"]
    key = ("ping", ip)
    if not force:
        v = _cache_get(key)
        if v is not None:
            return v
    res = ping_host(ip, timeout)
    _cache_set(key, res, ttl)
    return res


def check_tcp_port(host: str, port: int = 8002, timeout: float = 1.0) -> bool:
    """Attempt a TCP connection to (host, port) to determine if something is listening.

    Returns True if connection succeeds, False otherwise.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def cached_check_tcp_port(
    host: str,
    port: int = 8002,
    timeout: float = 1.0,
    ttl: int | None = None,
    force: bool = False,
) -> bool:
    if ttl is None:
        ttl = DEFAULT_CACHE_TTL["tcp"]
    key = ("tcp", host, port)
    if not force:
        v = _cache_get(key)
        if v is not None:
            return v
    res = check_tcp_port(host, port, timeout)
    _cache_set(key, res, ttl)
    return res


def check_websocket_endpoint(
    host: str, port: int = 8002, token: str | None = None, timeout: float = 1.0
) -> bool:
    """Check whether the Samsung TV WebSocket endpoint accepts the given token.

    Uses SamsungTVWS + open() — the same path as actual command execution — so
    a True result here means commands will also succeed.
    Falls back to a plain TCP check only when samsungtvws is not installed and
    no token is being validated.
    """
    try:
        from samsungtvws import SamsungTVWS
    except ImportError:
        # Library not installed; can't validate token, fall back to TCP
        if token is not None:
            return False
        return check_tcp_port(host, port, timeout=timeout)

    try:
        client = SamsungTVWS(
            host=host,
            port=port,
            token=token,
            timeout=timeout,
            name=APP_NAME,
        )
        client.open()
        client.close()
        return True
    except Exception:
        return False


def cached_check_websocket_endpoint(
    host: str,
    port: int = 8002,
    token: str | None = None,
    timeout: float = 1.0,
    ttl: int | None = None,
    force: bool = False,
) -> bool:
    """Cached wrapper around check_websocket_endpoint; token included in key."""
    if ttl is None:
        ttl = DEFAULT_CACHE_TTL["token"]
    key = ("token", host, port, token)
    if not force:
        v = _cache_get(key)
        if v is not None:
            return v
    res = check_websocket_endpoint(host, port, token, timeout)
    _cache_set(key, res, ttl)
    return res


def query_tv_info(
    host: str, port: int = 8002, token: str | None = None, timeout: float = 2.0
) -> dict:
    """Attempt to query TV for more detailed info via a websocket client.

    This uses `samsungtvws` if available and attempts common methods like
    `device_info`, `get_device_info`, or `info`. Returns a dict of info on
    success, or raises an exception on failure.
    """
    import importlib

    try:
        samsung = importlib.import_module("samsungtvws")
    except Exception as e:
        raise RuntimeError("samsungtvws not installed") from e

    # Candidate client class names and info call names
    client_class_names = ("SamsungTVWS", "SamsungTV", "Television", "TV", "Client")
    # include 'rest_device_info' which is present on SamsungTVWS
    info_method_names = (
        "rest_device_info",
        "get_device_info",
        "device_info",
        "info",
        "status",
        "get_status",
    )

    # Try the TV's configured port first, then fallbacks (8001, 8002)
    ports_to_try = []
    if port:
        ports_to_try.append(port)
    ports_to_try.extend([8001, 8002])
    ports_to_try = list(dict.fromkeys(ports_to_try))  # dedupe, preserve order

    errors = []

    for cls_name in client_class_names:
        cls = getattr(samsung, cls_name, None)
        if not cls:
            continue
        for p in ports_to_try:
            try:
                # instantiate
                try:
                    client = cls(host=host, token=token, port=p)
                except TypeError:
                    try:
                        client = cls(host, p)
                        if token and hasattr(client, "authenticate"):
                            client.authenticate(token)
                    except Exception:
                        client = cls(host, p, token)

                # connect if available
                if hasattr(client, "connect"):
                    client.connect(timeout=timeout)

                # try info methods
                for m in info_method_names:
                    if hasattr(client, m):
                        meth = getattr(client, m)
                        try:
                            result = meth()
                            # close and return
                            if hasattr(client, "close"):
                                client.close()
                            # ensure result is a dict for our API
                            if isinstance(result, dict):
                                return result
                            # try to coerce to dict
                            return {"result": result}
                        except Exception as e:
                            errors.append(f"method {m} raised: {e}")
                            continue

                # No info method worked
                if hasattr(client, "close"):
                    client.close()
                errors.append(
                    f"client {cls_name} connected on port {p} but no info methods succeeded"
                )
            except Exception as e:
                errors.append(f"client {cls_name} failed on port {p}: {e}")
                continue

    raise RuntimeError("No usable samsungtvws client class found: " + "; ".join(errors))


def cached_query_tv_info(
    host: str,
    port: int = 8002,
    token: str | None = None,
    timeout: float = 2.0,
    ttl: int | None = None,
    force: bool = False,
) -> dict:
    """Cached wrapper around query_tv_info."""
    if ttl is None:
        ttl = DEFAULT_CACHE_TTL["info"]
    key = ("info", host, port, token)
    if not force:
        v = _cache_get(key)
        if v is not None:
            return v
    res = query_tv_info(host, port, token, timeout)
    _cache_set(key, res, ttl)
    return res


def get_power_state(
    host: str, port: int = 8002, token: str | None = None, timeout: float = 2.0
) -> str | None:
    """Get the current power state of the TV.

    Returns power state string (e.g., 'on', 'standby') or None if unavailable.
    """
    try:
        info = query_tv_info(host, port, token, timeout)
        # Check for PowerState field
        if "PowerState" in info:
            return info["PowerState"]
        # Check for device info structure
        if "device" in info and isinstance(info["device"], dict):
            return info["device"].get("PowerState")
        return None
    except Exception:
        return None


def cached_get_power_state(
    host: str,
    port: int = 8002,
    token: str | None = None,
    timeout: float = 2.0,
    ttl: int | None = None,
    force: bool = False,
) -> str | None:
    """Cached wrapper around get_power_state."""
    if ttl is None:
        ttl = DEFAULT_CACHE_TTL["info"]
    key = ("power", host, port, token)
    if not force:
        v = _cache_get(key)
        if v is not None:
            return v
    res = get_power_state(host, port, token, timeout)
    _cache_set(key, res, ttl)
    return res


def toggle_power(
    host: str,
    port: int = 8002,
    token: str | None = None,
    timeout: float = 15.0,
    retries: int = 2,
) -> bool:
    """Toggle TV power state.

    Returns True if command was sent successfully, raises exception on failure.
    """
    from samsungtvws import SamsungTVWS
    import time

    last_error = None

    # Try different key names as some TVs are picky
    keys_to_try = ["KEY_POWER", "KEY_POWEROFF"]

    for attempt in range(retries):
        try:
            client = SamsungTVWS(
                host=host,
                port=port,
                token=token,
                timeout=timeout,
                name=APP_NAME,
            )

            # Explicitly open and wait a moment
            client.open()
            time.sleep(1)  # Give it a second to stabilize after handshake

            success = False
            for key in keys_to_try:
                try:
                    client.send_key(key)
                    success = True
                    break
                except Exception as key_err:
                    last_error = key_err
                    if "timeOut" not in str(key_err):
                        break  # If it's not a timeout, trying another key might not help
                    continue

            client.close()
            if success:
                return True
            else:
                raise last_error

        except Exception as e:
            last_error = e
            error_str = str(e)

            # protocol level timeouts or busy signals
            if any(
                x in error_str
                for x in ["timeOut", "timeout", "busy", "Channel not found"]
            ):
                if attempt < retries - 1:
                    time.sleep(5)
                    continue

            if attempt == retries - 1:
                # Provide more diagnostic info
                msg = f"Failed to send power command. Error: {error_str}. "
                if "timeOut" in error_str:
                    msg += "The TV did not respond to the remote control request. Ensure your token is valid and 'Remote Access' is allowed in TV settings."
                raise RuntimeError(msg)

    if last_error:
        raise last_error
    return False


def send_key_command(
    host: str,
    key: str,
    port: int = 8002,
    token: str | None = None,
    timeout: float = 5.0,
) -> bool:
    """Send a key command to a Samsung TV.
    
    Args:
        host: TV IP address
        key: Key command to send (e.g., 'KEY_POWER', 'KEY_MUTE', 'KEY_VOLUP')
        port: WebSocket port (default 8002)
        token: Authentication token
        timeout: Connection timeout
        
    Returns:
        True if command was sent successfully
        
    Raises:
        Exception on failure
    """
    from samsungtvws import SamsungTVWS
    import time

    try:
        client = SamsungTVWS(
            host=host,
            port=port,
            token=token,
            timeout=timeout,
            name=APP_NAME,
        )

        client.open()
        time.sleep(0.5)  # Brief stabilization delay
        client.send_key(key)
        client.close()
        return True
        
    except Exception as e:
        raise RuntimeError(f"Failed to send key '{key}' to {host}: {e}")


def request_new_token(
    host: str, port: int = 8002, app_name: str = "TokenRequest", timeout: float = 30.0
) -> str:
    """Request a new token from Samsung TV by initiating pairing.

    This will attempt to connect without a token, triggering the pairing prompt on the TV.
    The user must accept the pairing on the TV within the timeout period.

    Args:
        host: TV IP address
        port: WebSocket port (default 8002)
        app_name: App name shown on TV pairing prompt
        timeout: Timeout in seconds to wait for pairing

    Returns:
        The new token string

    Raises:
        RuntimeError: If pairing fails or times out
    """
    try:
        import websocket
        import ssl
        import json
        import base64
    except ImportError as e:
        raise RuntimeError(f"Required modules not available: {e}")

    # Encode app name like the working script
    app_name_encoded = base64.b64encode(app_name.encode("utf-8")).decode("utf-8")
    uri = f"wss://{host}:{port}/api/v2/channels/samsung.remote.control?name={app_name_encoded}"

    ws = None
    try:
        ws = websocket.create_connection(
            uri, timeout=timeout, sslopt={"cert_reqs": ssl.CERT_NONE}
        )
        # Some TVs send a preliminary event before ms.channel.connect, so loop
        # through up to 5 messages to find the one that carries the token.
        for _ in range(5):
            response = json.loads(ws.recv())
            event = response.get("event")
            token = response.get("data", {}).get("token")
            if event == "ms.channel.connect" and token:
                return token
            elif token and event != "ms.channel.timeOut":
                # Older firmware may skip the event field but still deliver token
                return token
            elif event == "ms.channel.timeOut":
                raise RuntimeError(
                    f"Pairing request timed out. You must accept the pairing prompt on the TV screen within {timeout}s."
                )
            # else: keep reading (preliminary event, e.g. ms.channel.ready)
        raise RuntimeError(f"TV did not deliver a token in 5 messages. Last response: {response}")
    except websocket.WebSocketTimeoutException:
        raise RuntimeError(
            f"Connection timed out after {timeout}s. TV may be off, in standby mode, or not responding. Ensure TV is fully ON and accept the pairing prompt on screen."
        )
    except websocket.WebSocketConnectionClosedException as e:
        raise RuntimeError(
            f"WebSocket connection closed: {e}. TV may have rejected the connection."
        )
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid response from TV: {e}")
    except Exception as e:
        raise RuntimeError(
            f"Pairing failed: {e}. Ensure TV is ON and you accept the pairing prompt on screen within {timeout}s."
        )
    finally:
        if ws:
            ws.close()
