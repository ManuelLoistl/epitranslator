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
import re
from typing import Iterator

import anthropic

from backend.prompt import build_system_prompt, build_user_message

# Matches a markdown code-fence line (```), optionally with a language tag.
_FENCE_RE = re.compile(r"^\s*```[\w+-]*\s*$")


def _strip_code_fences(chunks: Iterator[str]) -> Iterator[str]:
    """Stream text while removing a leading ```lang fence and a trailing ``` fence.

    Models reliably wrap generated code in a markdown fence even when told not
    to. We want bare code, so strip an opening fence (first line) and a closing
    fence (last line) as the text streams, using one line of look-ahead so the
    trailing fence can be dropped before it's emitted.
    """
    buf = ""
    first_line_handled = False
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
                    continue  # drop opening fence
            if held is not None:
                yield held + "\n"
            held = line

    # End of stream. `buf` is any trailing text after the last newline.
    if buf.strip() == "":
        if held is not None and not is_fence(held):
            yield held + "\n"
    elif is_fence(buf):
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

    def _raw() -> Iterator[str]:
        with client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield text

    yield from _strip_code_fences(_raw())


def config_summary() -> dict:
    return {
        "model": MODEL,
        "effort": EFFORT,
        "max_tokens": MAX_TOKENS,
        "thinking": "adaptive" if THINKING_ENABLED else "off",
        "api_key_present": api_key_present(),
    }
