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

import os
from typing import Iterator

import anthropic

from backend.prompt import build_system_prompt, build_user_message

# --- Configuration (env-overridable) ----------------------------------------
MODEL = os.environ.get("TRANSLATOR_MODEL", "claude-opus-4-8")
EFFORT = os.environ.get("TRANSLATOR_EFFORT", "high")  # low | medium | high | xhigh | max
MAX_TOKENS = int(os.environ.get("TRANSLATOR_MAX_TOKENS", "32000"))
# Adaptive thinking helps translation fidelity; disable with THINKING=off.
THINKING_ENABLED = os.environ.get("TRANSLATOR_THINKING", "adaptive").lower() != "off"

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
    user = build_user_message(source_code, source_language)

    kwargs = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": {"effort": EFFORT},
    }
    if THINKING_ENABLED:
        kwargs["thinking"] = {"type": "adaptive"}

    with client.messages.stream(**kwargs) as stream:
        for text in stream.text_stream:
            yield text


def config_summary() -> dict:
    return {
        "model": MODEL,
        "effort": EFFORT,
        "max_tokens": MAX_TOKENS,
        "thinking": "adaptive" if THINKING_ENABLED else "off",
        "api_key_present": api_key_present(),
    }
