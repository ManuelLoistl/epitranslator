import time

from fastapi.testclient import TestClient

import backend.app as appmod
from backend.app import app, _with_heartbeat
from backend import translator

client = TestClient(app)


def test_heartbeat_fills_silent_stretch():
    def slow_gen():
        yield "data: {\"a\": 1}\n\n"
        time.sleep(0.3)
        yield "data: {\"b\": 2}\n\n"

    out = list(_with_heartbeat(slow_gen(), interval=0.05))
    # Real frames arrive intact and in order.
    data = [f for f in out if f.startswith("data:")]
    assert data == ["data: {\"a\": 1}\n\n", "data: {\"b\": 2}\n\n"]
    # At least one SSE comment was emitted during the 0.3s silence,
    # positioned between the two data frames.
    pings = [i for i, f in enumerate(out) if f == ": ping\n\n"]
    assert pings, "expected a heartbeat during the silent stretch"
    assert out.index("data: {\"a\": 1}\n\n") < pings[0] < out.index("data: {\"b\": 2}\n\n")


def test_no_heartbeat_when_stream_is_fast():
    def fast_gen():
        yield "data: {\"a\": 1}\n\n"
        yield "data: {\"b\": 2}\n\n"

    out = list(_with_heartbeat(fast_gen(), interval=5.0))
    assert out == ["data: {\"a\": 1}\n\n", "data: {\"b\": 2}\n\n"]


def test_translate_stream_carries_heartbeats(monkeypatch):
    monkeypatch.setattr(appmod, "HEARTBEAT_SECONDS", 0.05)
    monkeypatch.setattr(translator, "api_key_present", lambda: True)

    def slow_stream(source_code, source_language=None, category=None):
        time.sleep(0.3)  # stand-in for the model's silent thinking phase
        yield "CODE"

    monkeypatch.setattr(translator, "stream_translation", slow_stream)
    monkeypatch.setattr(translator, "generate_report", lambda *a, **k: None)
    monkeypatch.setattr(translator, "generate_model_doc", lambda *a, **k: None)
    body = client.post("/api/translate", json={"source_code": "x"}).text
    assert ": ping" in body
    assert "CODE" in body
    assert '"done": true' in body
