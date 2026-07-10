"""
FastAPI entry point for the disease-model translator.

One real endpoint: POST /api/translate streams the translated code back via
Server-Sent Events. Everything else serves the single-page UI and exposes a
little config/health introspection to show what model is wired up.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import MutableHeaders

from backend import categories as categories_mod
from backend import prompt as prompt_assets
from backend import translator

logger = logging.getLogger("epitranslator")

app = FastAPI(title="EpiTranslator", version="0.1.0")

# Security headers on every response. A pragmatic CSP: it locks where the page
# may connect (connect-src 'self'), and blocks framing, plugins, and <base>
# tricks. 'unsafe-inline' stays only because the app's script/style are inline,
# so this narrows an XSS's blast radius rather than blocking inline injection
# outright. Applied as pure-ASGI middleware so it never buffers the SSE body.
_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'none'; "
        "frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


class SecurityHeadersMiddleware:
    """Stamp security headers on each HTTP response without touching the body."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for key, value in _SECURITY_HEADERS.items():
                    headers.setdefault(key, value)
            await send(message)

        await self.app(scope, receive, send_wrapper)


app.add_middleware(SecurityHeadersMiddleware)

# Cap on how many files one translation request may carry. Enforced here
# (authoritative) and surfaced via /api/health so the UI mirrors it.
MAX_FILES = 10
# Cap on total source size (characters) per request — a safety net against
# accidental/abusive huge pastes. Env-overridable.
MAX_SOURCE_CHARS = int(os.environ.get("MAX_SOURCE_CHARS", "600000"))
# Light in-memory per-IP rate limit: RATE_LIMIT_MAX requests per window seconds.
RATE_LIMIT_MAX = int(os.environ.get("RATE_LIMIT_MAX", "20"))
RATE_LIMIT_WINDOW = int(os.environ.get("RATE_LIMIT_WINDOW", "60"))
_rate_hits: dict[str, list[float]] = {}


def _client_ip(request: Request) -> str:
    """Best-effort real client IP for rate limiting.

    Behind a proxy (e.g. Railway's edge) the socket peer is the proxy, so every
    user would share one bucket. Prefer the first hop of X-Forwarded-For, which
    the proxy sets. For rate limiting only — X-Forwarded-For is client-spoofable
    and must not be used for anything security-sensitive.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limited(ip: str) -> bool:
    """True once this IP exceeds RATE_LIMIT_MAX requests within the window.

    Also evicts IPs whose timestamps have all aged out, so the map stays bounded
    by the number of *recently active* clients rather than every IP ever seen.
    """
    now = time.time()
    for stale in [k for k, ts in _rate_hits.items()
                  if all(now - t >= RATE_LIMIT_WINDOW for t in ts)]:
        del _rate_hits[stale]
    hits = [t for t in _rate_hits.get(ip, []) if now - t < RATE_LIMIT_WINDOW]
    hits.append(now)
    _rate_hits[ip] = hits
    return len(hits) > RATE_LIMIT_MAX

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/")
async def index() -> FileResponse:
    # no-store so the single-page app is never served stale during development.
    return FileResponse(
        str(_STATIC_DIR / "index.html"),
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/health")
async def health() -> dict:
    config = translator.config_summary()
    config["max_files"] = MAX_FILES
    return {
        "status": "ok",
        "config": config,
        "assets": prompt_assets.assets_status(),
        "categories": categories_mod.public_categories(),
    }


@app.get("/api/docs")
async def docs() -> dict:
    """In-app documentation. Currently the target schema reference, served from
    the same file that feeds the prompt (one source of truth)."""
    return {"schema": prompt_assets.schema_reference()}


@app.post("/api/translate")
async def translate(payload: dict, request: Request) -> StreamingResponse:
    """
    Stream a translation.

    Body: { "files": [{"filename": "...", "content": "..."}], ... } or the
    legacy { "source_code": "..." }; plus "source_language"/"category" (optional).
    Response: SSE stream of {"text": "..."} events, then {"done": true},
    or {"error": "..."} on failure.
    """
    ip = _client_ip(request)
    files = payload.get("files")
    too_many = isinstance(files, list) and len(files) > MAX_FILES
    if isinstance(files, list) and files:
        source_code = prompt_assets.render_source_files(files)
    else:
        source_code = (payload.get("source_code") or "").strip()
    too_large = len(source_code) > MAX_SOURCE_CHARS
    source_language = (payload.get("source_language") or "").strip() or None
    category = (payload.get("category") or "").strip() or None

    def event_stream():
        if _rate_limited(ip):
            yield _sse({"error": "Too many requests — please wait a minute and try again."})
            return
        if too_many:
            yield _sse({"error": f"Too many files (max {MAX_FILES})."})
            return
        if too_large:
            yield _sse({"error": f"Source is too large (max {MAX_SOURCE_CHARS:,} characters) — please trim the input."})
            return
        if not source_code:
            yield _sse({"error": "No source code provided."})
            return
        if not translator.api_key_present():
            yield _sse(
                {"error": "ANTHROPIC_API_KEY is not set on the server."}
            )
            return
        try:
            # 1. First attempt streams the bare model.py live to the code pane.
            code_parts = []
            for chunk in translator.stream_translation(
                source_code, source_language, category
            ):
                code_parts.append(chunk)
                yield _sse({"text": chunk})
            code = "".join(code_parts)
            # 2. A stream cut mid-response leaves truncated, non-building code. If it
            #    doesn't parse, regenerate (buffered) up to the attempt limit and
            #    swap the pane with the first complete result.
            attempt = 1
            while (
                not translator.is_complete_code(code)
                and attempt < translator.MAX_TRANSLATION_ATTEMPTS
            ):
                attempt += 1
                yield _sse({"retrying": attempt})
                code = "".join(
                    translator.stream_translation(
                        source_code, source_language, category
                    )
                )
                if translator.is_complete_code(code):
                    yield _sse({"replace": code})
            if not translator.is_complete_code(code):
                yield _sse(
                    {"error": "The translation kept coming back incomplete — please try again in a moment."}
                )
                return
            # 3. Separate structured call for the report; emit it if we got one.
            yield _sse({"status": "Writing translation report…"})
            report = translator.generate_report(
                source_code, code, source_language
            )
            if report is not None:
                yield _sse({"report": report})
            else:
                yield _sse({"report_error": True})
            yield _sse({"done": True})
        except Exception:  # full detail is logged; the client gets a generic message
            logger.exception("translation failed")
            yield _sse({"error": "Translation failed — please try again in a moment."})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"
