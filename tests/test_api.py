import pytest
from fastapi.testclient import TestClient

from app.main import app
import app.wol as wol
import app.utils as utils


client = TestClient(app)


def test_list_tvs():
    r = client.get("/api/tvs")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert any(tv["ip"] == "10.10.97.123" for tv in data)


def test_get_tv():
    r = client.get("/api/tvs/10.10.97.123")
    assert r.status_code == 200
    data = r.json()
    assert data["mac"] == "28:AF:42:4D:39:8E"


def test_wake_tv_unicast(monkeypatch):
    called = {}

    def fake_send_unicast(mac, target_ip, port):
        called["mac"] = mac
        called["ip"] = target_ip
        called["port"] = port

    monkeypatch.setattr(wol, "send_magic_packet_unicast", fake_send_unicast)

    r = client.post("/api/tvs/10.10.97.123/wake", json={"port": 9})
    assert r.status_code == 200
    assert called["mac"] == "28:AF:42:4D:39:8E"
    assert called["ip"] == "10.10.97.123"
    assert called["port"] == 9


def test_tvs_status(monkeypatch):
    # Make ping return True for one IP and False for another
    def fake_ping(ip, timeout=1.0):
        return ip == "10.10.97.123"

    def fake_ws(ip, port=8002, timeout=1.0):
        return ip == "10.10.97.123"

    def fake_token_ok(ip, port=8002, token=None, timeout=1.0):
        # token verification succeeds only for the known token for 10.10.97.123
        return token == "10132873"

    monkeypatch.setattr(utils, "cached_ping_host", fake_ping)
    monkeypatch.setattr(utils, "cached_check_tcp_port", fake_ws)
    monkeypatch.setattr(utils, "cached_check_websocket_endpoint", fake_token_ok)

    r = client.get("/api/tvs/status")
    assert r.status_code == 200
    data = r.json()
    # find the two sample TVs
    dvd = {tv["ip"]: tv for tv in data}
    assert dvd["10.10.97.123"]["online"] is True
    assert dvd["10.10.97.132"]["online"] is False
    assert dvd["10.10.97.123"]["ws_online"] is True
    assert dvd["10.10.97.132"]["ws_online"] is False
    assert dvd["10.10.97.123"]["token_verified"] is True
    assert dvd["10.10.97.132"]["token_verified"] is False


def test_config_served():
    r = client.get("/config/tvs.json")
    assert r.status_code == 200
    data = r.json()
    assert "tvs" in data
    assert isinstance(data["tvs"], dict)


def test_ws_check_uses_token(monkeypatch):
    called = []

    def fake_check(host, port, token=None, timeout=1.0, force=False):
        called.append((host, port, token, force))
        # Simulate success only when token matches the known TV token
        return token == "10132873" and port == 8002

    monkeypatch.setattr(utils, "cached_check_websocket_endpoint", fake_check)

    r = client.get("/api/tvs/10.10.97.123/ws-check")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert data[0]["ok"] is True
    assert called[0][2] == "10132873"

    # Check another TV that should fail
    r2 = client.get("/api/tvs/10.10.97.132/ws-check")
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2[0]["ok"] is False
    assert called[1][2] == "92106970"


def test_tv_info_endpoint(monkeypatch):
    # Fake query_tv_info to return device data
    def fake_query(host, port, token, timeout=2.0, force=False):
        return {"name": "B4 TV", "model": "QN75", "uptime": 12345}

    # Use the underlying query function so the cached wrapper will cache the result
    monkeypatch.setattr(utils, "query_tv_info", fake_query)

    r = client.get("/api/tvs/10.10.97.123/info")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["info"]["name"] == "B4 TV"

    # Simulate an error on the underlying function and force bypassing the cache
    def fake_query_err(host, port, token, timeout=2.0):
        raise RuntimeError("failed")

    monkeypatch.setattr(utils, "query_tv_info", fake_query_err)
    r2 = client.get("/api/tvs/10.10.97.123/info?force=true")
    assert r2.status_code == 200
    assert r2.json()["ok"] is False
