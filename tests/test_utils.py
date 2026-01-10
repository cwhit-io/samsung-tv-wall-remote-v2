import sys
import types

import pytest

from app import utils


def test_check_websocket_endpoint_falls_back_to_tcp(monkeypatch):
    called = {}

    def fake_tcp(host, port, timeout=1.0):
        called["tcp"] = (host, port, timeout)
        return True

    monkeypatch.setattr(utils, "check_tcp_port", fake_tcp)
    # Make importlib.import_module raise ImportError for samsungtvws to force fallback
    import importlib

    def fake_import(name):
        if name == "samsungtvws":
            raise ImportError("no such module")
        return importlib.import_module(name)

    monkeypatch.setattr(importlib, "import_module", fake_import)

    ok = utils.check_websocket_endpoint("10.10.97.123", port=8002, token=None)
    assert ok is True
    assert called["tcp"] == ("10.10.97.123", 8002, 1.0)


def test_check_websocket_endpoint_uses_samsungtvws(monkeypatch):
    calls = {}

    class FakeClient:
        def __init__(self, host=None, port=None, token=None):
            calls["init"] = (host, port, token)

        def connect(self, timeout=None):
            calls["connect"] = timeout

        def close(self):
            calls["close"] = True

    fake_module = types.SimpleNamespace(SamsungTVWS=FakeClient)

    monkeypatch.setitem(sys.modules, "samsungtvws", fake_module)

    ok = utils.check_websocket_endpoint("10.10.97.123", port=8002, token="10132873")
    assert ok is True
    assert calls["init"] == (None, None, "10132873") or calls["init"] == (
        "10.10.97.123",
        8002,
        "10132873",
    )
    assert "connect" in calls
    assert calls["close"] is True


def test_check_websocket_endpoint_token_validation_fails(monkeypatch):
    # Simulate samsungtvws available but connection fails with token
    class FakeClient:
        def __init__(self, host=None, port=None, token=None):
            pass

        def connect(self, timeout=None):
            raise Exception("Invalid token")

        def close(self):
            pass

    fake_module = types.SimpleNamespace(SamsungTVWS=FakeClient)

    monkeypatch.setitem(sys.modules, "samsungtvws", fake_module)

    ok = utils.check_websocket_endpoint("10.10.97.123", port=8002, token="invalid")
    assert ok is False
