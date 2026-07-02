from fastapi.testclient import TestClient

from backend.app import app, MAX_FILES
from backend import translator

client = TestClient(app)


def _post(json):
    return client.post("/api/translate", json=json).text


def test_health_includes_max_files():
    body = client.get("/api/health").json()
    assert body["config"]["max_files"] == MAX_FILES


def test_too_many_files_errors(monkeypatch):
    monkeypatch.setattr(translator, "api_key_present", lambda: True)
    files = [{"filename": f"f{i}.py", "content": "x"} for i in range(MAX_FILES + 1)]
    assert "Too many files" in _post({"files": files})


def test_files_are_rendered_and_streamed(monkeypatch):
    seen = {}
    monkeypatch.setattr(translator, "api_key_present", lambda: True)

    def fake_stream(source_code, source_language=None, category=None):
        seen["src"] = source_code
        yield "CODE"

    monkeypatch.setattr(translator, "stream_translation", fake_stream)
    monkeypatch.setattr(translator, "generate_report", lambda *a, **k: None)
    files = [{"filename": "model.R", "content": "dyn"},
             {"filename": "params.R", "content": "beta<-0.3"}]
    body = _post({"files": files})
    assert "=== file: model.R (R) ===" in seen["src"]
    assert "params.R" in seen["src"]
    assert "CODE" in body


def test_source_code_fallback_still_works(monkeypatch):
    seen = {}
    monkeypatch.setattr(translator, "api_key_present", lambda: True)

    def fake_stream(source_code, source_language=None, category=None):
        seen["src"] = source_code
        yield "OUT"

    monkeypatch.setattr(translator, "stream_translation", fake_stream)
    monkeypatch.setattr(translator, "generate_report", lambda *a, **k: None)
    body = _post({"source_code": "legacy"})
    assert seen["src"] == "legacy"
    assert "OUT" in body


def test_source_too_large(monkeypatch):
    import backend.app as appmod
    monkeypatch.setattr(translator, "api_key_present", lambda: True)
    monkeypatch.setattr(appmod, "MAX_SOURCE_CHARS", 10)
    appmod._rate_hits.clear()
    body = _post({"source_code": "x" * 50})
    assert "too large" in body.lower()


def test_rate_limit(monkeypatch):
    import backend.app as appmod
    monkeypatch.setattr(translator, "api_key_present", lambda: True)

    def fake_stream(source_code, source_language=None, category=None):
        yield "OUT"

    monkeypatch.setattr(translator, "stream_translation", fake_stream)
    monkeypatch.setattr(translator, "generate_report", lambda *a, **k: None)
    monkeypatch.setattr(appmod, "RATE_LIMIT_MAX", 2)
    appmod._rate_hits.clear()
    assert "OUT" in _post({"source_code": "a"})
    assert "OUT" in _post({"source_code": "b"})
    assert "Too many requests" in _post({"source_code": "c"})
