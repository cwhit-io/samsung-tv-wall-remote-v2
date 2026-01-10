import socket
import re
from typing import Optional


MAC_CLEAN_RE = re.compile(r"[^0-9A-Fa-f]")


def _normalize_mac(mac: str) -> bytes:
    """Return raw bytes from MAC address string like 'aa:bb:cc:11:22:33'"""
    cleaned = MAC_CLEAN_RE.sub("", mac)
    if len(cleaned) != 12:
        raise ValueError("MAC address must contain 12 hex digits")
    return bytes.fromhex(cleaned)


def send_magic_packet(mac: str, broadcast: str = "255.255.255.255", port: int = 9) -> None:
    """Send a Wake-on-LAN magic packet to the given MAC address.

    This uses a UDP broadcast to the provided address and port.
    """
    mac_bytes = _normalize_mac(mac)
    packet = b"\xff" * 6 + mac_bytes * 16

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast, port))
    finally:
        sock.close()


def send_magic_packet_unicast(mac: str, target_ip: str, port: int = 9) -> None:
    """Send a Wake-on-LAN magic packet directly (unicast) to target_ip:port."""
    mac_bytes = _normalize_mac(mac)
    packet = b"\xff" * 6 + mac_bytes * 16

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Do not set broadcast option for unicast
        sock.sendto(packet, (target_ip, port))
    finally:
        sock.close()
