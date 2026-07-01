"""Split a translation stream into the model.py code and the trailing report.

The model emits the bare model.py, then a sentinel line, then a JSON report.
`split_stream` streams the code out a line at a time as it arrives and yields the
accumulated report text once; `parse_report` turns that text into a dict.
"""
from __future__ import annotations

import json
import re
from typing import Iterable, Iterator, Optional, Tuple

SENTINEL = "# ---TRANSLATION-REPORT---"

# Tolerant sentinel matcher: the canonical form is `# ---TRANSLATION-REPORT---`,
# but models paraphrase the divider (e.g. `# ===TRANSLATION REPORT===`). We accept
# any leading `#`s, a run of >=2 `-`/`=` on each side, and TRANSLATION/REPORT split
# by a space, hyphen, or underscore. Matching loosely means a paraphrased report
# still gets stripped out of the code pane (it must never leak into model.py), even
# if its body then fails to parse as JSON.
_SENTINEL_RE = re.compile(
    r"^\s*#*\s*[-=]{2,}\s*TRANSLATION[\s_-]?REPORT\s*[-=]{2,}\s*$",
    re.IGNORECASE,
)


def _is_sentinel(line: str) -> bool:
    return _SENTINEL_RE.match(line) is not None


def split_stream(chunks: Iterable[str]) -> Iterator[Tuple[str, str]]:
    """Yield ("text", s) for model.py content and, if the sentinel line is seen,
    a final ("report", json_text) with everything after it.

    Line-aware: text is emitted one line at a time so the sentinel can be
    detected before it leaks into the code; everything after the sentinel line is
    accumulated and yielded once at end of stream.
    """
    buf = ""
    in_report = False
    report_parts = []

    for chunk in chunks:
        if in_report:
            report_parts.append(chunk)
            continue
        buf += chunk
        while True:
            nl = buf.find("\n")
            if nl == -1:
                break
            line, buf = buf[:nl], buf[nl + 1:]
            if _is_sentinel(line):
                in_report = True
                report_parts.append(buf)  # remainder after the sentinel newline
                buf = ""
                break
            yield ("text", line + "\n")

    if in_report:
        yield ("report", "".join(report_parts))
    elif _is_sentinel(buf):
        # Sentinel as the very last line with no trailing newline: empty report.
        yield ("report", "")
    elif buf:
        yield ("text", buf)


def parse_report(report_text: str) -> Optional[dict]:
    """Parse the report JSON. Returns None if empty, invalid, or not an object.

    Falls back to the outermost ``{...}`` span so a stray prefix/suffix (a code
    fence, a leading comment line) around otherwise-valid JSON still parses.
    """
    text = report_text.strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            obj = json.loads(text[start:end + 1])
        except (json.JSONDecodeError, ValueError):
            return None
    return obj if isinstance(obj, dict) else None
