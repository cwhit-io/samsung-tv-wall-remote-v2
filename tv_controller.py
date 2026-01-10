import argparse
import base64
import json
import os
import time
import websocket
import ssl
import socket
import concurrent.futures
from datetime import datetime
import subprocess
import platform

# --- Configuration ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TV_INFO_FILE = os.path.join(SCRIPT_DIR, "tvs.json")
TV_KEYS_FILE = os.path.join(SCRIPT_DIR, "tv_keys.json")
APP_NAME = "PythonController"
APP_NAME_ENCODED = base64.b64encode(APP_NAME.encode("utf-8")).decode("utf-8")


# --- Utility Functions ---
def load_tv_info():
    if os.path.exists(TV_INFO_FILE):
        with open(TV_INFO_FILE, "r") as f:
            return json.load(f)
    return {"tvs": {}}


def save_tv_info(tv_info):
    """Saves TV information to the JSON file."""
    with open(TV_INFO_FILE, "w") as f:
        json.dump(tv_info, f, indent=4)


def load_tv_keys():
    if os.path.exists(TV_KEYS_FILE):
        with open(TV_KEYS_FILE, "r") as f:
            return json.load(f).get("keys", {})
    # Default keys if file doesn't exist
    return {
        "power-on": "WOL",
        "power-off": "KEY_POWER",
        "volup": "KEY_VOLUP",
        "voldown": "KEY_VOLDOWN",
        "mute": "KEY_MUTE",
        "chup": "KEY_CHUP",
        "chdown": "KEY_CHDOWN",
        "menu": "KEY_MENU",
        "home": "KEY_HOME",
        "source": "KEY_SOURCE",
        "guide": "KEY_GUIDE",
        "up": "KEY_UP",
        "down": "KEY_DOWN",
        "left": "KEY_LEFT",
        "right": "KEY_RIGHT",
        "enter": "KEY_ENTER",
        "return": "KEY_RETURN",
        "hdmi1": "KEY_HDMI1",
        "hdmi2": "KEY_HDMI2",
        "hdmi3": "KEY_HDMI3",
        "hdmi4": "KEY_HDMI4",
    }


def save_tv_keys(tv_keys):
    with open(TV_KEYS_FILE, "w") as f:
        json.dump({"keys": tv_keys}, f, indent=4)


def get_tv_info(ip):
    return load_tv_info()["tvs"].get(ip)


def get_tv_name(ip):
    info = get_tv_info(ip)
    return info.get("name", f"Unknown TV ({ip})") if info else f"Unknown TV ({ip})"


def get_all_tvs():
    return list(load_tv_info()["tvs"].keys())


def update_tv_info(ip, **kwargs):
    tv_info = load_tv_info()
    if ip not in tv_info["tvs"]:
        print(f"Error: TV {ip} not found in {TV_INFO_FILE}")
        return
    tv_info["tvs"][ip].update(kwargs)
    tv_info["tvs"][ip]["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_tv_info(tv_info)


# --- Core Network Functions ---


def is_tv_on(tv_ip):
    """Pings the TV to check if it's responsive on the network."""
    try:
        param = "-n" if platform.system().lower() == "windows" else "-c"
        timeout_param = "-w" if platform.system().lower() == "windows" else "-W"
        command = ["ping", param, "1", timeout_param, "1", tv_ip]
        return (
            subprocess.run(
                command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            ).returncode
            == 0
        )
    except Exception:
        return False


def send_wol_packet(mac_address, broadcast_ip="255.255.255.255"):
    """Sends a Wake-on-LAN magic packet to a specific broadcast address."""
    try:
        mac_bytes = bytes.fromhex(mac_address.replace(":", "").replace("-", ""))
        if len(mac_bytes) != 6:
            raise ValueError("Invalid MAC")
        magic_packet = b"\xff" * 6 + mac_bytes * 16
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(magic_packet, (broadcast_ip, 9))
        return True, f"WOL packet sent to {broadcast_ip}"
    except Exception as e:
        return False, f"Error sending WOL packet: {e}"


def get_token(tv_ip, force_pairing=False):
    """Gets an authentication token, either from storage or by pairing."""
    tv_info = get_tv_info(tv_ip)
    if not tv_info:
        return None
    if not force_pairing and tv_info.get("token"):
        return tv_info["token"]

    uri = f"wss://{tv_ip}:8002/api/v2/channels/samsung.remote.control?name={APP_NAME_ENCODED}"
    print(f"PAIRING REQUIRED for {get_tv_name(tv_ip)}. Please approve on the TV.")
    ws = None
    try:
        ws = websocket.create_connection(
            uri, timeout=60, sslopt={"cert_reqs": ssl.CERT_NONE}
        )
        response = json.loads(ws.recv())
        if response.get("data", {}).get("token"):
            token = response["data"]["token"]
            update_tv_info(tv_ip, token=token)
            return token
    except Exception as e:
        print(f"Pairing error for {get_tv_name(tv_ip)}: {e}")
    finally:
        if ws:
            ws.close()
    return None


def send_command(tv_ip, command_key):
    """Sends a single command key to the TV via WebSocket."""
    token = get_token(tv_ip)
    if not token:
        return False, "Authentication token not available"

    uri = f"wss://{tv_ip}:8002/api/v2/channels/samsung.remote.control?name={APP_NAME_ENCODED}&token={token}"
    ws = None
    try:
        ws = websocket.create_connection(
            uri, timeout=5, sslopt={"cert_reqs": ssl.CERT_NONE}
        )
        response = json.loads(ws.recv())
        if response.get("event") != "ms.channel.connect":
            if response.get("event") == "ms.channel.unauthorized":
                update_tv_info(tv_ip, token=None)  # Clear bad token
            return False, response.get("message", "Connection issue")

        payload = {
            "method": "ms.remote.control",
            "params": {
                "Cmd": "Click",
                "DataOfCmd": command_key,
                "Option": "false",
                "TypeOfRemote": "SendRemoteKey",
            },
        }
        ws.send(json.dumps(payload))
        return True, f"Sent {command_key}"
    except Exception as e:
        return False, str(e)
    finally:
        if ws:
            ws.close()


# --- Command Processors ---
def handle_power_on(tv_ip):
    """
    Handles the power-on command. Sends WOL and verifies.
    If verification times out, it assumes success but notes the timeout.
    """
    name = get_tv_name(tv_ip)
    if is_tv_on(tv_ip):
        return {
            "ip": tv_ip,
            "name": name,
            "success": True,
            "message": "TV is already on.",
        }

    tv_info = get_tv_info(tv_ip)
    mac = tv_info.get("mac")
    if not mac:
        return {
            "ip": tv_ip,
            "name": name,
            "success": False,
            "message": "No MAC address configured.",
        }

    # Get broadcast IP from TV info, or use subnet default
    tv_broadcast_ip = tv_info.get("broadcast_ip", "10.10.111.255")
    success, msg = send_wol_packet(mac, broadcast_ip=tv_broadcast_ip)
    if not success:
        return {"ip": tv_ip, "name": name, "success": False, "message": msg}

    for _ in range(10):
        time.sleep(3)
        if is_tv_on(tv_ip):
            return {
                "ip": tv_ip,
                "name": name,
                "success": True,
                "message": "TV successfully powered on.",
            }

    return {
        "ip": tv_ip,
        "name": name,
        "success": True,
        "message": "WOL sent, but verification timed out. TV may be booting slowly.",
    }


def handle_power_off(tv_ip):
    """
    Handles power-off. A successful command send is the success metric,
    as pinging a TV in network standby can be unreliable.
    """
    name = get_tv_name(tv_ip)

    # First, check if the TV is even in a state to be controlled.
    if not is_tv_on(tv_ip):
        return {
            "ip": tv_ip,
            "name": name,
            "success": True,
            "message": "TV is already off (unresponsive to ping).",
        }

    # Attempt to send the power off command.
    success, msg = send_command(tv_ip, "KEY_POWER")

    # The result of send_command is our new source of truth.
    if success:
        return {
            "ip": tv_ip,
            "name": name,
            "success": True,
            "message": "Power-off command sent successfully.",
        }
    else:
        # This will catch issues like a bad token or network error.
        return {
            "ip": tv_ip,
            "name": name,
            "success": False,
            "message": f"Failed to send power-off command: {msg}",
        }


def process_generic_command(tv_ip, command_key):
    """Processes any command other than power-on/off."""
    name = get_tv_name(tv_ip)
    if not is_tv_on(tv_ip):
        return {"ip": tv_ip, "name": name, "success": False, "message": "TV is off."}
    success, msg = send_command(tv_ip, command_key)
    return {"ip": tv_ip, "name": name, "success": success, "message": msg}


# --- API-friendly wrapper functions (for main.py) ---
def send_key(tv_ip, key_code):
    """
    API-friendly wrapper for sending keys.
    Returns dict format expected by main.py
    """
    return process_generic_command(tv_ip, key_code)


def wake_tv(tv_ip):
    """
    API-friendly alias for handle_power_on.
    """
    return handle_power_on(tv_ip)


def power_on_tv(tv_ip):
    """
    API-friendly alias for handle_power_on.
    """
    return handle_power_on(tv_ip)


def power_off_tv(tv_ip):
    """
    API-friendly alias for handle_power_off.
    """
    return handle_power_off(tv_ip)


# --- Main Execution (CLI mode) ---
def main():
    tv_keys = load_tv_keys()
    parser = argparse.ArgumentParser(description="Control Samsung TVs concurrently.")
    parser.add_argument(
        "--command", choices=list(tv_keys.keys()), help="Command to send."
    )
    parser.add_argument("--target", help="Target TV IP(s), comma-separated or 'all'.")
    parser.add_argument("--list", action="store_true", help="List configured TVs.")
    parser.add_argument(
        "--list-commands", action="store_true", help="List available commands."
    )
    args = parser.parse_args()

    # Handle list arguments first
    if args.list_commands:
        print("\n===== AVAILABLE TV COMMANDS =====")
        for cmd, key in sorted(tv_keys.items()):
            print(f"  {cmd}: {key}")
        return

    if args.list:
        tv_info = load_tv_info()
        print("\n===== CONFIGURED TVs =====")
        for ip, info in tv_info.get("tvs", {}).items():
            print(
                f"\n{info.get('name', 'N/A')}\n  IP: {ip}\n  Model: {info.get('model', 'N/A')}\n  MAC: {info.get('mac', 'N/A')}\n  Token: {'Yes' if info.get('token') else 'No'}"
            )
        return

    # Now validate that command and target are provided for actual commands
    if not args.command or not args.target:
        parser.error(
            "--command and --target are required when not using --list or --list-commands"
        )

    targets = (
        get_all_tvs()
        if args.target == "all"
        else [ip.strip() for ip in args.target.split(",")]
    )

    command_map = {
        "power-on": handle_power_on,
        "power-off": handle_power_off,
    }

    # Determine the function to execute
    if args.command in command_map:
        target_func = command_map[args.command]
        params = [(ip,) for ip in targets]
    else:
        command_key = tv_keys.get(args.command)
        if not command_key:
            print(f"Error: Unknown command '{args.command}'.")
            return
        target_func = process_generic_command
        params = [(ip, command_key) for ip in targets]

    # Execute commands concurrently
    results = []
    print(f"\nExecuting '{args.command}' on {len(targets)} TV(s)...")
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(targets) or 1
    ) as executor:
        future_to_ip = {executor.submit(target_func, *p): p[0] for p in params}
        for future in concurrent.futures.as_completed(future_to_ip):
            try:
                results.append(future.result())
            except Exception as exc:
                ip = future_to_ip[future]
                results.append(
                    {
                        "ip": ip,
                        "name": get_tv_name(ip),
                        "success": False,
                        "message": str(exc),
                    }
                )

    # Print summary
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    print("\n===== COMMAND EXECUTION SUMMARY =====")
    print(f"Successful operations: {len(successful)}/{len(results)}")
    if successful:
        print("\nSuccessful Operations:")
        for r in sorted(successful, key=lambda x: x["name"]):
            print(f"  ✓ {r['name']} ({r['ip']}): {r['message']}")
    if failed:
        print("\nFailed Operations:")
        for r in sorted(failed, key=lambda x: x["name"]):
            print(f"  ✗ {r['name']} ({r['ip']}): {r['message']}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
