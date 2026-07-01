# Category Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional disease-category picker whose selection is fed to the translation prompt as a disambiguation hint.

**Architecture:** One source of truth (`backend/categories.py`) defines the list; `/api/health` exposes `{id,label}` for the UI dropdown; `prompt.py` uses the per-category `hint`; the choice flows UI → `/api/translate` payload → `translate()` → `stream_translation()` → `build_user_message()`.

**Tech Stack:** Python 3.9, FastAPI, vanilla HTML/JS, pytest.

## Global Constraints

- The category is a **disambiguation hint only** — the appended prompt line must instruct the model NOT to add compartments/parameters/mechanisms the source lacks; the source is authoritative.
- The hint goes in the **user message** (`build_user_message`), never the cached system prompt.
- Category is **optional**: missing/empty/unknown/`unspecified` → no hint, never an error.
- Single source of truth: the list lives only in `backend/categories.py`; the UI derives it from `/api/health` (no duplicate list in JS).
- Commits: per the user's workflow, get approval before each commit/push; work on `main`.

Spec: `docs/superpowers/specs/2026-07-01-category-picker-design.md`.

---

## File Structure

- **Create `backend/categories.py`** — `CATEGORIES` list of `{id,label,hint}` + `hint_for(id)` + `public_categories()`.
- **Modify `backend/prompt.py`** — `build_user_message(source_code, source_language, category)` appends the hint line.
- **Modify `backend/translator.py`** — `stream_translation(source_code, source_language, category)` threads `category` through.
- **Modify `backend/app.py`** — `/api/health` adds `categories`; `translate()` reads `category` from the payload and passes it on.
- **Modify `static/index.html`** — a `<select id="category">` populated from `/api/health`, sent in the POST body.
- **Modify `tests/test_prompt.py`** — add category/hint tests.
- **Create `tests/test_categories.py`** — `categories.py` unit tests.
- **Modify `docs/ROADMAP.md`, `README.md`** — mark #1 shipped; one README line.

---

## Task 1: Category data + prompt hint

**Files:**
- Create: `backend/categories.py`
- Modify: `backend/prompt.py` (`build_user_message`)
- Modify: `backend/translator.py` (`stream_translation`)
- Create: `tests/test_categories.py`
- Modify: `tests/test_prompt.py`

**Interfaces:**
- Produces:
  - `backend/categories.py`: `CATEGORIES: list[dict]` (each `{"id","label","hint"}`, `hint` is `str | None`), `hint_for(category_id: str | None) -> str | None`, `public_categories() -> list[dict]` (each `{"id","label"}`).
  - `build_user_message(source_code: str, source_language: str | None = None, category: str | None = None) -> str`.
  - `stream_translation(source_code: str, source_language: str | None = None, category: str | None = None)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_categories.py`:
```python
from backend.categories import CATEGORIES, hint_for, public_categories


def test_ids_unique_and_unspecified_first():
    ids = [c["id"] for c in CATEGORIES]
    assert len(ids) == len(set(ids))
    assert ids[0] == "unspecified"


def test_unspecified_has_no_hint():
    assert CATEGORIES[0]["hint"] is None
    assert hint_for("unspecified") is None


def test_hint_for_known_category():
    h = hint_for("waterborne")
    assert isinstance(h, str) and h.strip()


def test_hint_for_unknown_or_none():
    assert hint_for("nope") is None
    assert hint_for(None) is None
    assert hint_for("") is None


def test_public_categories_omit_hint_and_keep_order():
    pub = public_categories()
    assert pub[0] == {"id": "unspecified", "label": "Unspecified"}
    assert all(set(c.keys()) == {"id", "label"} for c in pub)
    assert len(pub) == len(CATEGORIES)
```

Append to `tests/test_prompt.py`:
```python
def test_user_message_appends_category_hint():
    from backend.prompt import build_user_message
    msg = build_user_message("print(1)", None, "waterborne")
    assert "Disease category hint" in msg
    assert "authoritative" in msg  # the "source is authoritative" guard


def test_user_message_no_hint_for_unspecified_or_unknown():
    from backend.prompt import build_user_message
    base = build_user_message("print(1)", None, None)
    assert base == build_user_message("print(1)", None, "unspecified")
    assert base == build_user_message("print(1)", None, "nope")
    assert "Disease category hint" not in base
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_categories.py tests/test_prompt.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.categories'` (and the two new prompt tests error on the 3-arg call).

- [ ] **Step 3: Create `backend/categories.py`**

```python
"""The single source of truth for the disease-category picker.

Categories are by transmission route. They are a disambiguation HINT fed to the
translation prompt — never a directive to invent structure. `unspecified` (the
default, first) adds no hint.
"""
from __future__ import annotations

from typing import List, Optional

CATEGORIES: List[dict] = [
    {"id": "unspecified", "label": "Unspecified", "hint": None},
    {"id": "respiratory", "label": "Respiratory / airborne",
     "hint": "a respiratory / airborne, person-to-person disease"},
    {"id": "direct_contact", "label": "Direct contact",
     "hint": "a directly contact-transmitted disease"},
    {"id": "vector_borne", "label": "Vector-borne",
     "hint": "a vector-borne disease (e.g. mosquito- or tick-transmitted)"},
    {"id": "waterborne", "label": "Waterborne / environmental",
     "hint": "a waterborne / environmental disease (it may involve an "
             "environmental reservoir)"},
    {"id": "sexually_transmitted", "label": "Sexually transmitted",
     "hint": "a sexually transmitted disease"},
    {"id": "zoonotic", "label": "Zoonotic / spillover",
     "hint": "a zoonotic disease with animal-reservoir spillover"},
]

_HINTS = {c["id"]: c["hint"] for c in CATEGORIES}


def hint_for(category_id: Optional[str]) -> Optional[str]:
    """Return the prompt hint for a category id, or None (unspecified/unknown)."""
    if not category_id:
        return None
    return _HINTS.get(category_id)


def public_categories() -> List[dict]:
    """The {id, label} list for the UI dropdown (hints stay server-side)."""
    return [{"id": c["id"], "label": c["label"]} for c in CATEGORIES]
```

- [ ] **Step 4: Wire the hint into `build_user_message` (`backend/prompt.py`)**

Add the import near the top of `backend/prompt.py` (with the other imports):
```python
from backend.categories import hint_for
```

Replace `build_user_message` with:
```python
def build_user_message(
    source_code: str,
    source_language: str | None = None,
    category: str | None = None,
) -> str:
    """Build the user turn: the source model to translate."""
    lang = (source_language or "").strip()
    header = (
        f"Translate the following disease model"
        + (f" (source language: {lang})" if lang else "")
        + " into the target schema. Output only the bare translated Python code."
    )
    parts = [f"{header}\n\n```\n{source_code.rstrip()}\n```"]
    hint = hint_for(category)
    if hint:
        parts.append(
            f"Disease category hint: this is {hint}. Use this only to "
            "disambiguate genuinely ambiguous cases; the source code is "
            "authoritative — do not add compartments, parameters, or mechanisms "
            "the source does not contain."
        )
    return "\n\n".join(parts)
```

- [ ] **Step 5: Thread `category` through `stream_translation` (`backend/translator.py`)**

In `backend/translator.py`, change the `stream_translation` signature and its `build_user_message` call:
```python
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
            "cache_control": {"type": "ephemeral"},
        }
    ]
    user = build_user_message(source_code, source_language, category)
```
(Leave the rest of `stream_translation` unchanged.)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_categories.py tests/test_prompt.py -q`
Expected: PASS (all category + prompt tests green).

- [ ] **Step 7: Commit** (get user approval first)

```bash
git add backend/categories.py backend/prompt.py backend/translator.py tests/test_categories.py tests/test_prompt.py
git commit -m "Add disease-category list and feed the selected hint into the prompt"
```

---

## Task 2: Expose categories on health + accept category in translate

**Files:**
- Modify: `backend/app.py`
- Modify: `tests/test_prompt.py` (add a health test — reuses the FastAPI app)

**Interfaces:**
- Consumes: `backend.categories.public_categories`, `translator.stream_translation(..., category)` (Task 1).
- Produces: `/api/health` response gains `categories: [{id,label}]`; `POST /api/translate` reads `category` from the JSON body.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_prompt.py`:
```python
def test_health_includes_categories():
    from fastapi.testclient import TestClient
    from backend.app import app
    r = TestClient(app).get("/api/health")
    body = r.json()
    assert "categories" in body
    assert body["categories"][0] == {"id": "unspecified", "label": "Unspecified"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/test_prompt.py::test_health_includes_categories -q`
Expected: FAIL — `KeyError: 'categories'` (also installs/uses `httpx` via `fastapi.testclient`; if missing, `pip install httpx` first).

- [ ] **Step 3: Add categories to `/api/health` and read `category` in `translate` (`backend/app.py`)**

Add the import near the other `from backend import ...` lines:
```python
from backend import categories as categories_mod
```

In the `health()` function, add a `categories` key:
```python
@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "config": translator.config_summary(),
        "assets": prompt_assets.assets_status(),
        "categories": categories_mod.public_categories(),
    }
```

In `translate()`, read `category` from the payload (next to `source_language`) and pass it into `stream_translation`:
```python
    source_code = (payload.get("source_code") or "").strip()
    source_language = (payload.get("source_language") or "").strip() or None
    category = (payload.get("category") or "").strip() or None
```
and in `event_stream`, change the streaming call:
```python
            for chunk in translator.stream_translation(
                source_code, source_language, category
            ):
                code_parts.append(chunk)
                yield _sse({"text": chunk})
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/ -q`
Expected: PASS (full suite green).

- [ ] **Step 5: Commit** (get user approval first)

```bash
git add backend/app.py tests/test_prompt.py
git commit -m "Expose categories on /api/health and accept category in /api/translate"
```

---

## Task 3: UI dropdown + docs

**Files:**
- Modify: `static/index.html`
- Modify: `docs/ROADMAP.md`, `README.md`

**Interfaces:**
- Consumes: `/api/health` `categories` (Task 2); the `category` request field (Task 2).

Note: browser UI — verification is manual.

- [ ] **Step 1: Add the `<select>` to the source pane header**

In `static/index.html`, replace the source `.pane-head` block:
```html
      <div class="pane-head">
        <label for="source">Source model</label>
        <input type="text" id="lang" placeholder="language (optional)" />
      </div>
```
with:
```html
      <div class="pane-head">
        <label for="source">Source model</label>
        <span style="display:flex; gap:8px; align-items:center;">
          <select id="category" title="Disease category (optional hint)"></select>
          <input type="text" id="lang" placeholder="language (optional)" />
        </span>
      </div>
```

Add CSS for the select inside the `<style>` block (after the `.pane-head input[type=text]` rule):
```css
  .pane-head select {
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 12px;
  }
```

- [ ] **Step 2: Populate the dropdown from health and send the category**

In `static/index.html` `loadConfig()`, after the existing `$("meta").innerHTML = ...` assignment (still inside the `try`), populate the select:
```javascript
    const sel = $("category");
    for (const c of (j.categories || [])) {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = c.label;
      sel.appendChild(opt);
    }
```

In `translate()`, include the category in the POST body:
```javascript
      body: JSON.stringify({
        source_code,
        source_language: $("lang").value.trim(),
        category: $("category").value,
      }),
```

- [ ] **Step 3: Manual verification in the browser**

Run: `source .venv/bin/activate && uvicorn backend.app:app --port 8021`
Open `http://localhost:8021`. Confirm:
- The **category dropdown** appears in the source pane header, defaults to **Unspecified**, and lists the 7 categories.
- Translate the epicookbook SIR with **Unspecified** → works as before.
- Pick **Waterborne / environmental**, translate a minimal cholera-ish source → still a valid `model.py`; the report drawer still appears.
- Open devtools Network → the `/api/translate` request body includes `"category":"waterborne"`.
Stop the server when done.

- [ ] **Step 4: Update docs**

In `docs/ROADMAP.md`, under item **### 1. Category picker on submit**, add a line:
`> **Shipped 2026-07-01.** List lives in backend/categories.py (the schema defines no category taxonomy, so open-question #3 is resolved: there is nothing to sync with). Optional, default Unspecified; feeds a disambiguation hint into the user message.`

In `README.md`, under "How it works", add one line: the source pane has an optional **disease-category** picker (by transmission route) that feeds a disambiguation hint into the translation; it never overrides the source.

- [ ] **Step 5: Commit** (get user approval first)

```bash
git add static/index.html docs/ROADMAP.md README.md
git commit -m "Add category dropdown to the UI and document the picker"
```

---

## Self-Review notes (author)

- **Spec coverage:** category list + single source (Task 1 `categories.py`); prompt hint with the "source is authoritative" guard (Task 1 `build_user_message`); threading through `stream_translation` (Task 1) and `translate()` (Task 2); `/api/health` exposure (Task 2); UI dropdown from health + payload field (Task 3); optional/graceful (covered by `hint_for` returning None for unknown/empty and the tests); docs (Task 3). All covered.
- **Type consistency:** `hint_for`, `public_categories`, `CATEGORIES`, and the `category` param name are used identically across tasks and tests.
- **No new deps at runtime;** `fastapi.testclient` needs `httpx` (dev-only) — flagged in Task 2 Step 2.
