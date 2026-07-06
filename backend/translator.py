"""
The Claude call. Streams the translated code back token by token.

Design notes (grounded in the current Anthropic API):
- We use the official ``anthropic`` SDK with ``client.messages.stream(...)`` and
  forward only ``text_stream`` — so the model's thinking blocks never reach the
  user, just the final code.
- Adaptive thinking + high effort are on by default: faithful model translation
  is exactly the kind of "remotely complicated" task that benefits, and because
  we only forward text deltas the thinking stays invisible.
- The model is a single swappable env var (TRANSLATOR_MODEL). "Try a few models"
  is just changing that value and redeploying — no code edit.
- The schema + examples sit in the system prompt with a cache breakpoint, so
  repeat translations reuse the cached prefix and only pay for the source code.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Iterator, Optional

import anthropic

logger = logging.getLogger("epitranslator")

from backend.prompt import (
    build_system_prompt,
    build_user_message,
    build_report_system_prompt,
    build_report_user_message,
)

# Matches a markdown code-fence line (```), optionally with a language tag.
_FENCE_RE = re.compile(r"^\s*```[\w+-]*\s*$")


def _strip_code_fences(chunks: Iterator[str]) -> Iterator[str]:
    """Stream text while removing a leading ```lang fence and a trailing ``` fence.

    Models reliably wrap generated code in a markdown fence even when told not
    to. We want bare code, so strip an opening fence (first line) and a closing
    fence (last line) as the text streams, using one line of look-ahead so the
    trailing fence can be dropped before it's emitted.

    The trailing fence is only stripped when an opening fence was actually
    consumed, so bare code that legitimately ends in a ``` line (e.g. the last
    line of a docstring, or a stream truncated mid-string) is left intact.
    """
    buf = ""
    first_line_handled = False
    opened = False  # True once we've consumed a leading ``` fence
    held: str | None = None  # last completed line, held back for look-ahead

    def is_fence(s: str) -> bool:
        return _FENCE_RE.match(s) is not None

    for chunk in chunks:
        buf += chunk
        while True:
            nl = buf.find("\n")
            if nl == -1:
                break
            line, buf = buf[:nl], buf[nl + 1:]
            if not first_line_handled:
                first_line_handled = True
                if is_fence(line):
                    opened = True
                    continue  # drop opening fence
            if held is not None:
                yield held + "\n"
            held = line

    # End of stream. `buf` is any trailing text after the last newline.
    # Only strip a trailing fence if an opening fence was actually consumed;
    # otherwise a lone ``` that is real code would be silently dropped.
    if buf.strip() == "":
        if held is not None and not (opened and is_fence(held)):
            yield held + "\n"
    elif opened and is_fence(buf):
        if held is not None:
            yield held + "\n"
    else:
        if held is not None:
            yield held + "\n"
        yield buf

# --- Configuration (env-overridable) ----------------------------------------
MODEL = os.environ.get("TRANSLATOR_MODEL", "claude-opus-4-8")
EFFORT = os.environ.get("TRANSLATOR_EFFORT", "high")  # low | medium | high | xhigh | max
MAX_TOKENS = int(os.environ.get("TRANSLATOR_MAX_TOKENS", "32000"))
# Adaptive thinking helps translation fidelity; disable with THINKING=off.
THINKING_ENABLED = os.environ.get("TRANSLATOR_THINKING", "adaptive").lower() != "off"

# The translation report is a separate, cheaper structured call.
REPORT_MODEL = os.environ.get("TRANSLATOR_REPORT_MODEL", MODEL)
REPORT_EFFORT = os.environ.get("TRANSLATOR_REPORT_EFFORT", "low")
REPORT_MAX_TOKENS = int(os.environ.get("TRANSLATOR_REPORT_MAX_TOKENS", "8000"))

# JSON schema the report call is constrained to (structured outputs). Every
# object sets additionalProperties=False and lists its required keys, per the
# structured-outputs rules. `value` is a string to avoid number/string unions.
_ORIGIN = {"type": "string", "enum": ["source", "converted", "derived", "guessed"]}
_ELEMENT_REQUIRED = ["origin", "note"]
REPORT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["attention", "compartments", "parameters", "interventions"],
    "properties": {
        "attention": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["severity", "category", "title", "detail"],
                "properties": {
                    "severity": {"type": "string", "enum": ["high", "info"]},
                    "category": {
                        "type": "string",
                        "enum": [
                            "no_dynamics",
                            "invented",
                            "dropped_structure",
                            "model_mismatch",
                            "ambiguity",
                        ],
                    },
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                },
            },
        },
        "compartments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["schema_id", "source_name", "origin", "note"],
                "properties": {
                    "schema_id": {"type": "string"},
                    "source_name": {"type": ["string", "null"]},
                    "origin": _ORIGIN,
                    "note": {"type": "string"},
                },
            },
        },
        "parameters": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["schema_name", "source_name", "value", "unit", "origin", "note"],
                "properties": {
                    "schema_name": {"type": "string"},
                    "source_name": {"type": ["string", "null"]},
                    "value": {"type": "string"},
                    "unit": {"type": "string"},
                    "origin": _ORIGIN,
                    "note": {"type": "string"},
                },
            },
        },
        "interventions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["schema_id", "source_name", "target_rates", "origin", "note"],
                "properties": {
                    "schema_id": {"type": "string"},
                    "source_name": {"type": ["string", "null"]},
                    "target_rates": {"type": "array", "items": {"type": "string"}},
                    "origin": _ORIGIN,
                    "note": {"type": "string"},
                },
            },
        },
    },
}

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        # Zero-arg client resolves ANTHROPIC_API_KEY from the environment.
        _client = anthropic.Anthropic()
    return _client


def api_key_present() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def stream_translation(
    source_code: str,
    source_language: str | None = None,
    category: str | None = None,
) -> Iterator[str]:
    """Yield translated code as text chunks. Raises on API/auth errors."""
    client = _get_client()

    system = [
        {
            "type": "text",
            "text": build_system_prompt(),
            # Cache the instructions + schema + examples prefix across requests.
            "cache_control": {"type": "ephemeral"},
        }
    ]
    user = build_user_message(source_code, source_language, category)

    kwargs = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": {"effort": EFFORT},
    }
    if THINKING_ENABLED:
        kwargs["thinking"] = {"type": "adaptive"}

    def _raw() -> Iterator[str]:
        with client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield text

    yield from _strip_code_fences(_raw())


def generate_report(
    source_code: str,
    model_code: str,
    source_language: str | None = None,
) -> Optional[dict]:
    """Second call: read source + generated model.py, return the report as a dict.

    Uses structured outputs (``output_config.format`` with a JSON schema) so the
    response is guaranteed to be a single JSON object matching REPORT_SCHEMA — it
    cannot leak into the code and cannot be prose. Returns None on any failure so
    the translation still succeeds without a report.
    """
    if not model_code.strip():
        return None
    try:
        client = _get_client()
        resp = client.messages.create(
            model=REPORT_MODEL,
            max_tokens=REPORT_MAX_TOKENS,
            system=build_report_system_prompt(),
            messages=[
                {
                    "role": "user",
                    "content": build_report_user_message(
                        source_code, model_code, source_language
                    ),
                }
            ],
            output_config={
                "effort": REPORT_EFFORT,
                "format": {"type": "json_schema", "schema": REPORT_SCHEMA},
            },
        )
        text = next((b.text for b in resp.content if b.type == "text"), None)
        if not text:
            return None
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:  # never let the report break a successful translation
        logger.exception("report generation failed")
        return None


def config_summary() -> dict:
    return {
        "model": MODEL,
        "effort": EFFORT,
        "max_tokens": MAX_TOKENS,
        "thinking": "adaptive" if THINKING_ENABLED else "off",
        "api_key_present": api_key_present(),
    }
