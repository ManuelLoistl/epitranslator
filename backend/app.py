"""
FastAPI entry point for the disease-model translator.

One real endpoint: POST /api/translate streams the translated code back via
Server-Sent Events. Everything else serves the single-page UI and exposes a
little config/health introspection so you can see what model is wired up.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend import prompt as prompt_assets
from backend import report as report_mod
from backend import translator

logger = logging.getLogger("model-translator")

app = FastAPI(title="Disease Model Translator", version="0.1.0")

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(str(_STATIC_DIR / "index.html"))


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "config": translator.config_summary(),
        "assets": prompt_assets.assets_status(),
    }


@app.post("/api/translate")
async def translate(payload: dict) -> StreamingResponse:
    """
    Stream a translation.

    Body: { "source_code": "...", "source_language": "R" (optional) }
    Response: SSE stream of {"text": "..."} events, then {"done": true},
    or {"error": "..."} on failure.
    """
    source_code = (payload.get("source_code") or "").strip()
    source_language = (payload.get("source_language") or "").strip() or None

    def event_stream():
        if not source_code:
            yield _sse({"error": "No source code provided."})
            return
        if not translator.api_key_present():
            yield _sse(
                {"error": "ANTHROPIC_API_KEY is not set on the server."}
            )
            return
        try:
            chunks = translator.stream_translation(source_code, source_language)
            yield from _translation_events(chunks)
            yield _sse({"done": True})
        except Exception as exc:  # surface a clean message to the UI
            logger.exception("translation failed")
            yield _sse({"error": f"{type(exc).__name__}: {str(exc)[:400]}"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _translation_events(chunks):
    """Turn a translation stream into SSE strings: {text} per code line, and one
    {report} when the model emits a valid JSON report block."""
    for kind, payload in report_mod.split_stream(chunks):
        if kind == "text":
            yield _sse({"text": payload})
        else:  # "report"
            parsed = report_mod.parse_report(payload)
            if parsed is not None:
                yield _sse({"report": parsed})


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"
