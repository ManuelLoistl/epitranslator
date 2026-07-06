"""The security-headers middleware stamps a CSP + hardening headers on every
response (the static UI and the JSON APIs alike)."""
from fastapi.testclient import TestClient

from backend.app import app

client = TestClient(app)


def test_headers_on_index():
    r = client.get("/")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    csp = r.headers.get("content-security-policy")
    assert csp
    for directive in ("default-src 'self'", "connect-src 'self'",
                      "object-src 'none'", "base-uri 'none'",
                      "frame-ancestors 'none'"):
        assert directive in csp
    # index() sets its own Cache-Control; the middleware must not clobber it.
    assert r.headers.get("cache-control") == "no-store"


def test_headers_on_api():
    r = client.get("/api/health")
    assert r.headers.get("content-security-policy")
    assert r.headers.get("x-content-type-options") == "nosniff"
