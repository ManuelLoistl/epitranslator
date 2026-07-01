"""Split a translation stream into the model.py code and the trailing report.

The model emits the bare model.py, then a sentinel line, then a JSON report.
`split_stream` streams the code out a line at a time as it arrives and yields the
accumulated report text once; `parse_report` turns that text into a dict.
"""
from __future__ import annotations

import json
from typing import Iterable, Iterator, Optional, Tuple

SENTINEL = "# ---TRANSLATION-REPORT---"


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
            if line.strip() == SENTINEL:
                in_report = True
                report_parts.append(buf)  # remainder after the sentinel newline
                buf = ""
                break
            yield ("text", line + "\n")

    if in_report:
        yield ("report", "".join(report_parts))
    elif buf.strip() == SENTINEL:
        # Sentinel as the very last line with no trailing newline: empty report.
        yield ("report", "")
    elif buf:
        yield ("text", buf)


def parse_report(report_text: str) -> Optional[dict]:
    """Parse the report JSON. Returns None if empty, invalid, or not an object."""
    text = report_text.strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None
