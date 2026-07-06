"""Tests for the per-IP rate limiter: real-client-IP extraction (so the limit
works behind a proxy) and eviction of stale IPs (so the map stays bounded)."""
import types

from backend import app


class FakeReq:
    def __init__(self, headers=None, client_host=None):
        self.headers = headers or {}
        self.client = types.SimpleNamespace(host=client_host) if client_host else None


def test_client_ip_prefers_first_forwarded_hop():
    r = FakeReq(headers={"x-forwarded-for": "203.0.113.7, 10.0.0.1"}, client_host="10.0.0.1")
    assert app._client_ip(r) == "203.0.113.7"


def test_client_ip_falls_back_to_socket_peer():
    r = FakeReq(headers={}, client_host="198.51.100.9")
    assert app._client_ip(r) == "198.51.100.9"


def test_client_ip_unknown_when_no_client():
    assert app._client_ip(FakeReq(headers={}, client_host=None)) == "unknown"


def test_rate_limit_trips_after_max():
    app._rate_hits.clear()
    ip = "9.9.9.9"
    results = [app._rate_limited(ip) for _ in range(app.RATE_LIMIT_MAX + 1)]
    assert not any(results[:app.RATE_LIMIT_MAX])   # first MAX allowed
    assert results[-1] is True                     # MAX+1 tripped


def test_stale_ips_are_evicted():
    app._rate_hits.clear()
    app._rate_hits["1.1.1.1"] = [0.0]   # ancient timestamp, fully expired
    app._rate_limited("2.2.2.2")        # any call triggers the sweep
    assert "1.1.1.1" not in app._rate_hits
    assert "2.2.2.2" in app._rate_hits
