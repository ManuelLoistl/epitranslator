# Translation Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After each translation, surface an attention banner + an expandable audit of every compartment, parameter, and intervention translation (with provenance), driven by a model-emitted JSON report — without changing the copyable `model.py`.

**Architecture:** The model emits the bare `model.py`, then a sentinel line, then a JSON report. A new pure module (`backend/report.py`) splits the stream (code vs. report); the SSE endpoint streams code as `{text}` events and emits a `{report}` event at the end; the UI renders a banner + audit panel from it. The report instruction lives in a NEW appended prompt-asset file so the existing prompt files stay stable.

**Tech Stack:** Python 3.9, FastAPI, the `anthropic` SDK (streaming), vanilla HTML/JS (single page), pytest for tests.

## Global Constraints

- **Prompt stability (project rule, see `CLAUDE.md`):** do not edit the existing prompt files beyond the single approved one-line `system_prompt.md` softening; all new prompt behavior goes in the new appended file `prompt_assets/output_report.md`.
- **Log prompt changes:** any change to a prompt file MUST be recorded in `docs/prompt-change-log.md`.
- **Commits need the user's go-ahead:** per the user's workflow, get approval before each commit/push. Commit steps below are grouped one-per-task so approval is per task. Push directly to `main`, no PRs.
- **Graceful degradation is mandatory:** if the model emits no sentinel or invalid JSON, the app must behave exactly as today (code only, no report). The feature must never break a translation.
- **Sentinel string (exact, used verbatim everywhere):** `# ---TRANSLATION-REPORT---`
- **`origin` vocabulary:** `source` | `converted` | `derived` | `guessed`.
- **`attention.category` vocabulary:** `no_dynamics` | `invented` | `dropped_structure` | `model_mismatch` | `ambiguity`; `attention.severity`: `high` | `info`.

Spec: `docs/superpowers/specs/2026-07-01-translation-report-design.md`.

---

## File Structure

- **Create `backend/report.py`** — pure stream-splitter: `SENTINEL`, `split_stream()`, `parse_report()`. No FastAPI/Anthropic imports. Fully unit-testable.
- **Modify `backend/app.py`** — add module-level `_translation_events()` that uses `report.split_stream`/`parse_report`; refactor `event_stream()` to delegate to it and emit `{report}` before `{done}`.
- **Create `prompt_assets/output_report.md`** — the report instruction (prompt content), appended to the system prompt.
- **Modify `backend/prompt.py`** — read + append `output_report.md` as the final system-prompt section; add `output_report_present` to `assets_status()`.
- **Modify `prompt_assets/system_prompt.md`** — one-line softening of the "Output only" instruction (logged).
- **Modify `static/index.html`** — consume the `{report}` event; render the attention banner + audit panel; add CSS.
- **Create `requirements-dev.txt`** — `pytest` (test-only dependency).
- **Create `tests/test_report.py`, `tests/test_app_events.py`, `tests/test_prompt.py`** — unit tests.
- **Modify `docs/prompt-change-log.md`, `docs/ROADMAP.md`, `README.md`** — finalize log entry + note the feature.

---

## Task 1: Stream-splitter module (`backend/report.py`)

**Files:**
- Create: `backend/report.py`
- Create: `requirements-dev.txt`
- Test: `tests/test_report.py`

**Interfaces:**
- Produces:
  - `SENTINEL: str` = `"# ---TRANSLATION-REPORT---"`
  - `split_stream(chunks: Iterable[str]) -> Iterator[tuple[str, str]]` — yields `("text", s)` for code pieces (line-granular) and, if the sentinel line appears, a final `("report", json_text)` with everything after it.
  - `parse_report(report_text: str) -> Optional[dict]` — `json.loads` of the text; returns `None` if empty, invalid JSON, or not a JSON object.

- [ ] **Step 1: Create the dev requirements file and install pytest**

Create `requirements-dev.txt`:
```
pytest>=8.0
```
Run: `source .venv/bin/activate && pip install -r requirements-dev.txt`
Expected: pytest installs successfully.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_report.py`:
```python
from backend.report import SENTINEL, split_stream, parse_report


def collect(chunks):
    return list(split_stream(chunks))


def test_no_sentinel_streams_all_text():
    assert collect(["import x\n", "y = 1\n"]) == [
        ("text", "import x\n"),
        ("text", "y = 1\n"),
    ]


def test_no_sentinel_no_trailing_newline_flushes_tail():
    assert collect(["a\n", "b"]) == [("text", "a\n"), ("text", "b")]


def test_sentinel_splits_code_from_report():
    out = collect(["code\n", SENTINEL + "\n", '{"a": 1}'])
    assert out == [("text", "code\n"), ("report", '{"a": 1}')]


def test_sentinel_split_across_chunks():
    out = collect(["code\n# ---TRANSLATION", "-REPORT---\n", "{}"])
    assert out == [("text", "code\n"), ("report", "{}")]


def test_report_accumulates_across_chunks():
    out = collect(["c\n", SENTINEL + "\n", '{"a":', "1}"])
    assert out == [("text", "c\n"), ("report", '{"a":1}')]


def test_parse_report_valid():
    assert parse_report('{"a": 1}') == {"a": 1}


def test_parse_report_malformed_returns_none():
    assert parse_report("{not json") is None


def test_parse_report_empty_returns_none():
    assert parse_report("   ") is None


def test_parse_report_non_object_returns_none():
    assert parse_report("[1, 2]") is None
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_report.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.report'`.

- [ ] **Step 4: Implement `backend/report.py`**

Create `backend/report.py`:
```python
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_report.py -v`
Expected: PASS (9 passed).

- [ ] **Step 6: Commit** (get user approval first)

```bash
git add backend/report.py requirements-dev.txt tests/test_report.py
git commit -m "Add stream-splitter for the translation report"
```

---

## Task 2: Wire the split into the SSE endpoint (`backend/app.py`)

**Files:**
- Modify: `backend/app.py`
- Test: `tests/test_app_events.py`

**Interfaces:**
- Consumes: `backend.report.split_stream`, `backend.report.parse_report` (Task 1).
- Produces:
  - `_translation_events(chunks: Iterable[str]) -> Iterator[str]` — module-level; yields SSE strings (`data: {...}\n\n`), emitting `{"text": ...}` per code line and one `{"report": {...}}` when a valid report is present (nothing when absent/invalid).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_app_events.py`:
```python
import json

from backend.app import _translation_events
from backend.report import SENTINEL


def events(chunks):
    return [json.loads(s[len("data:"):].strip()) for s in _translation_events(chunks)]


def test_text_only_when_no_report():
    assert events(["code\n", "more\n"]) == [
        {"text": "code\n"},
        {"text": "more\n"},
    ]


def test_emits_report_event_after_text():
    chunks = ["code\n", SENTINEL + "\n", '{"attention": [], "parameters": []}']
    assert events(chunks) == [
        {"text": "code\n"},
        {"report": {"attention": [], "parameters": []}},
    ]


def test_malformed_report_is_dropped():
    chunks = ["code\n", SENTINEL + "\n", "{not json"]
    assert events(chunks) == [{"text": "code\n"}]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_app_events.py -v`
Expected: FAIL — `ImportError: cannot import name '_translation_events'`.

- [ ] **Step 3: Add `_translation_events` and refactor `event_stream`**

In `backend/app.py`, add this import near the top (with the other `from backend import ...` lines):
```python
from backend import report as report_mod
```

Add this module-level function just above the existing `def _sse(obj: dict) -> str:`:
```python
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
```

Replace the body of `event_stream()` inside `translate()` (currently the `try` block that loops over `translator.stream_translation(...)`) with:
```python
        try:
            chunks = translator.stream_translation(source_code, source_language)
            yield from _translation_events(chunks)
            yield _sse({"done": True})
        except Exception as exc:  # surface a clean message to the UI
            logger.exception("translation failed")
            yield _sse({"error": f"{type(exc).__name__}: {str(exc)[:400]}"})
```
(Leave the two guard checks above it — the empty-source and missing-key `yield _sse({"error": ...}); return` — unchanged.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_app_events.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Sanity-check the app still imports and serves health**

Run: `source .venv/bin/activate && python -c "from backend.app import app; print('ok')"`
Expected: prints `ok` with no import errors.

- [ ] **Step 6: Commit** (get user approval first)

```bash
git add backend/app.py tests/test_app_events.py
git commit -m "Emit a report SSE event from the split translation stream"
```

---

## Task 3: Prompt changes — new report file + assembly + one-line softening

**Files:**
- Create: `prompt_assets/output_report.md`
- Modify: `backend/prompt.py`
- Modify: `prompt_assets/system_prompt.md` (one line)
- Modify: `docs/prompt-change-log.md`
- Test: `tests/test_prompt.py`

**Interfaces:**
- Consumes: `backend.report.SENTINEL` (for the test assertion only).
- Produces: `build_system_prompt()` output now contains the sentinel + report instruction; `assets_status()` gains `output_report_present: bool`.

- [ ] **Step 1: Create the report instruction file**

Create `prompt_assets/output_report.md`:
```markdown
## Output addendum — translation report

After the complete `model.py`, emit one line containing exactly:

    # ---TRANSLATION-REPORT---

then a single JSON object (no code fences, nothing after it) describing what the
translation did. The app parses this to show the user what needs attention and
to audit every mapping. It is NOT part of `model.py`.

Shape:

    {
      "attention": [
        {"severity": "high|info", "category": "...", "title": "...", "detail": "..."}
      ],
      "compartments": [
        {"schema_id": "...", "source_name": "... or null", "origin": "...", "note": "..."}
      ],
      "parameters": [
        {"schema_name": "...", "source_name": "... or null", "value": <number or string>,
         "unit": "...", "origin": "...", "note": "..."}
      ],
      "interventions": [
        {"schema_id": "...", "source_name": "... or null", "target_rates": ["..."],
         "origin": "...", "note": "..."}
      ]
    }

Rules:
- List EVERY declared compartment, parameter/edge rate, and intervention — a
  complete audit, not only the noteworthy ones.
- `origin` is one of:
  - "source"    — taken directly from the source model.
  - "converted" — same quantity, unit-transformed (period↔rate, %↔fraction).
  - "derived"   — computed or restructured from the source (e.g. beta from R0, or
                  a compartment split for a competing-risks branch).
  - "guessed"   — NOT in the source; invented as a plausible default.
  (Compartments use source/derived/guessed; interventions use source/guessed.)
- `source_name` is the name in the source, or null if it has no counterpart.
- `note` is a short (<= ~15 word) explanation; use "" when there is nothing to add.
- `attention` flags what the user should review. `severity` is "high" (could be
  wrong / needs a human decision) or "info" (a faithful simplification worth
  knowing). `category` is one of:
  - "no_dynamics"       — the source contained no model dynamics (e.g. a run
                          wrapper); compartments/rates were INFERRED, not
                          translated. Always "high"; say so plainly.
  - "invented"          — one or more guessed compartments/parameters/interventions.
  - "dropped_structure" — structure simplified away (age, stochasticity, spatial
                          coupling, non-exponential delays, interventions).
  - "model_mismatch"    — the source is a different model class (agent-based,
                          inference, state-space) reduced to a compartmental core.
  - "ambiguity"         — a genuine interpretation choice was made.
- Always emit the report block. `attention` may be []. Emit valid JSON: double
  quotes, no trailing commas, no comments.

Example (abbreviated):

    # ---TRANSLATION-REPORT---
    {"attention":[{"severity":"info","category":"dropped_structure","title":"Deterministic reduction","detail":"Source was stochastic; rendered as an ODE."}],"compartments":[{"schema_id":"S","source_name":"S","origin":"source","note":""},{"schema_id":"I","source_name":"I","origin":"source","note":""},{"schema_id":"R","source_name":"R","origin":"source","note":""}],"parameters":[{"schema_name":"beta","source_name":"b","value":0.1,"unit":"per day","origin":"source","note":""},{"schema_name":"gamma","source_name":"g","value":0.05,"unit":"per day","origin":"source","note":""}],"interventions":[]}
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_prompt.py`:
```python
from backend.prompt import build_system_prompt, assets_status
from backend.report import SENTINEL


def test_system_prompt_includes_report_instruction():
    prompt = build_system_prompt()
    assert SENTINEL in prompt
    assert "translation report" in prompt.lower()


def test_assets_status_reports_output_report_present():
    status = assets_status()
    assert status["output_report_present"] is True
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_prompt.py -v`
Expected: FAIL — `SENTINEL` not in prompt / `KeyError: 'output_report_present'`.

- [ ] **Step 4: Wire the new file into `backend/prompt.py`**

In `backend/prompt.py`, add the file path constant next to `_SCHEMA_FILE`:
```python
_OUTPUT_REPORT_FILE = _ASSETS / "output_report.md"
```

In `build_system_prompt()`, after the `examples` block is appended (just before `return`), append the report instruction as the final section:
```python
    report_instr = _strip_html_comments(_read(_OUTPUT_REPORT_FILE))
    if report_instr:
        parts.append(report_instr)
```

In `assets_status()`, add to the returned dict:
```python
        "output_report_present": _OUTPUT_REPORT_FILE.is_file()
        and bool(_strip_html_comments(_read(_OUTPUT_REPORT_FILE))),
```

- [ ] **Step 5: Make the one-line softening in `system_prompt.md`**

In `prompt_assets/system_prompt.md`, replace:
```
Output **only** the complete contents of `model.py` — bare Python source,
ready to save. No prose, no explanation, no markdown code fences. (The
```
with:
```
Output the complete contents of `model.py` — bare Python source, ready to
save — then the translation-report addendum described at the end of this
prompt (after a sentinel line). No prose or explanation around the code, and
no markdown code fences around it. (The
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_prompt.py -v`
Expected: PASS (2 passed).

- [ ] **Step 7: Finalize the change-log entry**

In `docs/prompt-change-log.md`, change the planned entry's status line from:
```
**Status: planned — not yet implemented.**
```
to:
```
**Status: implemented 2026-07-01.**
```
and under it add the exact `system_prompt.md` before/after from Step 5 (the two code blocks above), plus a line: "New file `prompt_assets/output_report.md` added and appended by `build_system_prompt()`."

- [ ] **Step 8: Commit** (get user approval first)

```bash
git add prompt_assets/output_report.md prompt_assets/system_prompt.md backend/prompt.py tests/test_prompt.py docs/prompt-change-log.md
git commit -m "Add translation-report prompt addendum and wire it into the system prompt"
```

---

## Task 4: UI — attention banner + audit panel (`static/index.html`)

**Files:**
- Modify: `static/index.html`

**Interfaces:**
- Consumes: the `{report}` SSE event (Task 2) with `{attention, compartments, parameters, interventions}`.

Note: this is a browser UI task; verification is manual (no JS test harness in this project). Steps show the exact code to add.

- [ ] **Step 1: Add CSS for the banner and panel**

In `static/index.html`, inside the `<style>` block (before `</style>`), add:
```css
  .report { border-top: 1px solid var(--border); background: var(--panel); }
  .banner { display: flex; flex-direction: column; gap: 6px; padding: 10px 16px; }
  .banner:empty { display: none; }
  .att { border-radius: 6px; padding: 8px 10px; font-size: 12px; cursor: pointer; }
  .att .att-title { font-weight: 600; }
  .att .att-detail { color: var(--muted); margin-top: 4px; display: none; }
  .att.open .att-detail { display: block; }
  .att.high { background: #3a2016; border: 1px solid var(--accent); }
  .att.info { background: #1f2733; border: 1px solid var(--border); color: var(--muted); }
  .audit-bar { padding: 8px 16px; font-size: 12px; color: var(--muted); cursor: pointer;
               border-top: 1px solid var(--border); user-select: none; }
  .audit-body { display: none; max-height: 40vh; overflow: auto; padding: 0 16px 12px; }
  .audit-body.open { display: block; }
  .audit-body h4 { font-size: 12px; color: var(--muted); margin: 12px 0 4px; }
  table.audit { width: 100%; border-collapse: collapse; font-size: 12px; }
  table.audit td, table.audit th { text-align: left; padding: 4px 6px;
               border-bottom: 1px solid var(--border); vertical-align: top; }
  .badge { font-size: 10px; padding: 1px 6px; border-radius: 10px; }
  .badge.guessed { background: var(--accent); color: #fff; }
  .badge.derived, .badge.converted { background: #2b3645; color: var(--text); }
  .badge.source { background: transparent; color: var(--muted); }
```

- [ ] **Step 2: Add the report DOM under the output pane**

In `static/index.html`, replace the output `<section class="pane">` (the one containing `<pre id="output">`) so it includes the report containers after the `<pre>`:
```html
    <section class="pane">
      <div class="pane-head">
        <label>Translated (target schema)</label>
        <button class="secondary" id="copy" style="padding:4px 10px;font-size:12px;font-weight:500;">Copy</button>
      </div>
      <pre id="output"></pre>
      <div class="report" id="report" style="display:none;">
        <div class="banner" id="banner"></div>
        <div class="audit-bar" id="auditBar"></div>
        <div class="audit-body" id="auditBody"></div>
      </div>
    </section>
```

- [ ] **Step 3: Add the render logic and wire the `{report}` event**

In `static/index.html` `<script>`, add these render helpers before `async function translate()`:
```javascript
function resetReport() {
  $("report").style.display = "none";
  $("banner").innerHTML = "";
  $("auditBody").innerHTML = "";
  $("auditBody").classList.remove("open");
  $("auditBar").textContent = "";
}

function renderReport(r) {
  const att = r.attention || [];
  const banner = $("banner");
  banner.innerHTML = "";
  for (const a of att) {
    const el = document.createElement("div");
    el.className = "att " + (a.severity === "high" ? "high" : "info");
    el.innerHTML = `<div class="att-title">${escapeHtml(a.title || "")}</div>` +
                   `<div class="att-detail">${escapeHtml(a.detail || "")}</div>`;
    el.addEventListener("click", () => el.classList.toggle("open"));
    banner.appendChild(el);
  }

  const groups = [
    ["Compartments", r.compartments || [], (x) => [x.source_name, x.schema_id]],
    ["Parameters", r.parameters || [], (x) => [x.source_name, x.schema_name,
      x.value !== undefined ? String(x.value) : "", x.unit || ""]],
    ["Interventions", r.interventions || [], (x) => [x.source_name, x.schema_id,
      (x.target_rates || []).join(", ")]],
  ];
  const total = groups.reduce((n, g) => n + g[1].length, 0);
  const body = $("auditBody");
  body.innerHTML = "";
  for (const [name, rows] of groups) {
    if (!rows.length) continue;
    const h = document.createElement("h4");
    h.textContent = name;
    body.appendChild(h);
    const table = document.createElement("table");
    table.className = "audit";
    for (const row of rows) {
      const tr = document.createElement("tr");
      const cells = groups.find((g) => g[0] === name)[2](row);
      const mapping = (cells[0] ? escapeHtml(cells[0]) + " → " : "") + escapeHtml(cells[1] || "");
      const extra = cells.slice(2).filter(Boolean).map(escapeHtml).join(" · ");
      tr.innerHTML =
        `<td>${mapping}</td>` +
        `<td>${extra}</td>` +
        `<td><span class="badge ${row.origin || "source"}">${escapeHtml(row.origin || "source")}</span></td>` +
        `<td>${escapeHtml(row.note || "")}</td>`;
      table.appendChild(tr);
    }
    body.appendChild(table);
  }

  $("auditBar").textContent = `Translation audit (${total}) ▸`;
  $("report").style.display = total || att.length ? "block" : "none";
}

function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
```

Wire the audit bar toggle once, next to the other listeners near the bottom of the script:
```javascript
$("auditBar").addEventListener("click", () => {
  const open = $("auditBody").classList.toggle("open");
  $("auditBar").textContent = $("auditBar").textContent.replace(/[▸▾]$/, open ? "▾" : "▸");
});
```

In `translate()`, call `resetReport();` right after `$("output").textContent = "";`. In the SSE event loop, add a handler for the report event alongside the existing ones:
```javascript
        if (evt.report) { renderReport(evt.report); }
```

- [ ] **Step 4: Manual verification in the browser**

Run: `source .venv/bin/activate && uvicorn backend.app:app --port 8001`
Open `http://localhost:8001`, paste the epicookbook SIR source (below), click Translate:
```python
import numpy as np
from scipy.integrate import solve_ivp
def sir_ode(times, init, parms):
    b, g = parms
    S, I, R = init
    return [-b*S*I, b*S*I - g*I, g*I]
parms = [0.1, 0.05]; init = [0.99, 0.01, 0]
```
Expected: code streams into `<pre>`; a banner appears (e.g. an `info`/`invented` item); an *"Translation audit (N) ▸"* bar appears; clicking it expands Compartments / Parameters tables with origin badges (guessed highlighted). Clicking a banner item expands its detail. Copy still copies only the code. Stop the server when done.

- [ ] **Step 5: Commit** (get user approval first)

```bash
git add static/index.html
git commit -m "Render attention banner and translation audit panel in the UI"
```

---

## Task 5: End-to-end verification and docs

**Files:**
- Modify: `README.md`, `docs/ROADMAP.md`, `docs/prompt-change-log.md`

- [ ] **Step 1: Run the full unit test suite**

Run: `source .venv/bin/activate && python -m pytest -v`
Expected: all tests pass (report + app-events + prompt).

- [ ] **Step 2: Live emission check on representative sources**

Start the server (`uvicorn backend.app:app --port 8001`). Translate each and confirm the report:
- **epicookbook SIR** (above) → full audit of S/I/R + beta/gamma; `origin` mostly `source`; no crash.
- **`.../scratchpad/sources/mpox_run.R`** → a `high` `no_dynamics` attention item stating the model was inferred, not translated; invented compartments/params flagged `guessed`.
- **`.../scratchpad/sources/wuhan_seir.R`** → beta shows `origin: derived` (from R0); a `dropped_structure` or `info` item.
Confirm in each: the code pane is clean bare `model.py` (no sentinel/JSON leaked), and the banner/panel populate. Stop the server.

- [ ] **Step 3: Graceful-degradation check**

Temporarily rename `prompt_assets/output_report.md` to `output_report.md.bak`, restart the server, translate the SIR source, and confirm the app behaves exactly as before (code only, no banner/panel, no errors). Then restore the file.
Run: `mv prompt_assets/output_report.md prompt_assets/output_report.md.bak` … test … `mv prompt_assets/output_report.md.bak prompt_assets/output_report.md`
Expected: translation still works; no `{report}` event; UI shows only code.

- [ ] **Step 4: Update user-facing docs**

In `README.md`, under "How it works", add one line: the output pane now also shows an attention banner and an expandable audit of every compartment/parameter/intervention translation (with provenance), driven by a report the model appends after the code.

In `docs/ROADMAP.md`, add a short note under the post-v1 section that this ships part of the "surface what needs attention / honest parameters" intent (relates to items #4 and #10).

In `docs/prompt-change-log.md`, append a one-line "Verified 2026-07-01: live emission confirmed on epicookbook SIR, mpox_run (no_dynamics), and wuhan_seir (derived beta)." to the (now implemented) output-addendum entry.

- [ ] **Step 5: Commit** (get user approval first)

```bash
git add README.md docs/ROADMAP.md docs/prompt-change-log.md
git commit -m "Document the translation-report feature and record verification"
```

---

## Self-Review notes (author)

- **Spec coverage:** two-tier UX (Task 4), report data model incl. compartments/parameters/interventions (Task 3 prompt + Task 4 render), sentinel split + graceful degradation (Tasks 1–2, Task 5 Step 3), new-file prompt approach + one-line softening + logging (Task 3), wiring checklist (Tasks 2–4), testing (Tasks 1–2 unit, Task 4 manual, Task 5 e2e). All covered.
- **Provenance for non-parameters:** compartments use source/derived/guessed; interventions use source/guessed — encoded in `output_report.md` (Task 3 Step 1) and rendered generically by badge class (Task 4).
- **Type consistency:** `SENTINEL`, `split_stream`, `parse_report`, `_translation_events` names are used identically across Tasks 1–3 and tests.
