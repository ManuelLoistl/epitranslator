# Multi-file Input Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Let a modeler submit a disease model as a set of files (upload or
paste), concatenated with headers into one source string, producing a single
`model.py`.

**Architecture:** Frontend posts `files: [{filename, content}]`;
`render_source_files()` glues them into one headered string that flows through
the existing, unchanged translation + report pipeline. Cap `MAX_FILES = 10`
enforced in the backend and mirrored to the UI via `/api/health`. New model
guidance lives in an appended prompt-asset file (no edits to existing prompts).

**Tech Stack:** FastAPI, vanilla JS SPA, pytest, Anthropic SDK.

## Global Constraints

- Do NOT edit the existing prompt files (`system_prompt.md`, `target_schema.py`,
  `examples/`). New model guidance goes in a NEW appended file.
- Log the new prompt-asset file in `docs/prompt-change-log.md`.
- `MAX_FILES = 10`.
- Single-unnamed-file input must stay byte-identical to today's single paste.
- Every new symbol wired to a reader in the same task.

---

### Task 1: `render_source_files()` in `backend/prompt.py`

**Files:**
- Modify: `backend/prompt.py`
- Test: `tests/test_prompt.py`

**Interfaces:**
- Produces: `render_source_files(files: list[dict]) -> str`, where each dict is
  `{"filename": str, "content": str}`. Reused by `app.py` (Task 3).

- [ ] **Step 1: Write failing tests**

```python
def test_render_single_unnamed_is_verbatim():
    from backend.prompt import render_source_files
    assert render_source_files([{"filename": "", "content": "print(1)\n"}]) == "print(1)\n"

def test_render_single_named_has_header():
    from backend.prompt import render_source_files
    out = render_source_files([{"filename": "model.R", "content": "x<-1"}])
    assert "=== file: model.R (R) ===" in out
    assert "x<-1" in out

def test_render_multiple_files_in_order_with_langs():
    from backend.prompt import render_source_files
    out = render_source_files([
        {"filename": "model.R", "content": "dyn"},
        {"filename": "params.csv", "content": "beta,0.3"},
    ])
    assert out.index("model.R") < out.index("params.csv")
    assert "=== file: model.R (R) ===" in out
    assert "=== file: params.csv (CSV) ===" in out

def test_render_drops_blank_and_empty():
    from backend.prompt import render_source_files
    assert render_source_files([]) == ""
    assert render_source_files([{"filename": "a.py", "content": "   "}]) == ""

def test_render_unknown_extension_omits_lang():
    from backend.prompt import render_source_files
    out = render_source_files([{"filename": "notes", "content": "hi"},
                               {"filename": "b.py", "content": "z"}])
    assert "=== file: notes ===" in out  # no "(...)" when no known ext
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/test_prompt.py -k render -v`
Expected: FAIL (render_source_files not defined).

- [ ] **Step 3: Implement**

Add to `backend/prompt.py` (uses existing `language_for_extension`):

```python
def render_source_files(files: List[dict]) -> str:
    """Concatenate submitted files into one source string.

    Each file is {"filename": str, "content": str}. Blank-content files are
    dropped. A single file with no filename is returned verbatim (byte-identical
    to a plain single paste, preserving the prompt cache). Otherwise each file is
    emitted under a `=== file: <name> (<Lang>) ===` header, in order.
    """
    kept = [f for f in files if (f.get("content") or "").strip()]
    if not kept:
        return ""
    if len(kept) == 1 and not (kept[0].get("filename") or "").strip():
        return kept[0]["content"]

    blocks: List[str] = []
    for f in kept:
        name = (f.get("filename") or "").strip() or "untitled"
        suffix = Path(name).suffix
        lang = language_for_extension(suffix) if suffix else ""
        label = f"{name} ({lang})" if lang else name
        blocks.append(f"=== file: {label} ===\n{f['content'].rstrip()}")
    return "\n\n".join(blocks)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_prompt.py -k render -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit** (deferred — batch commit after user approval).

---

### Task 2: Appended guidance prompt-asset file

**Files:**
- Create: `prompt_assets/multi_file_guidance.md`
- Modify: `backend/prompt.py` (`build_system_prompt`, `assets_status`)
- Test: `tests/test_prompt.py`

**Interfaces:**
- Produces: `_MULTI_FILE_FILE` appended in `build_system_prompt()`;
  `assets_status()["multi_file_guidance_present"]`.

- [ ] **Step 1: Write failing tests**

```python
def test_system_prompt_includes_multifile_guidance():
    p = build_system_prompt().lower()
    assert "several files" in p or "multiple files" in p

def test_assets_status_reports_multifile_present():
    assert assets_status()["multi_file_guidance_present"] is True
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/pytest tests/test_prompt.py -k multifile -v`
Expected: FAIL.

- [ ] **Step 3: Create the guidance file**

`prompt_assets/multi_file_guidance.md`:

```markdown
## When multiple files are provided

When the source is provided as several files (each under a `=== file: ... ===`
header), treat them together as one model:

- The file that defines the **dynamics** is authoritative for the model
  structure (compartments and flows).
- **Parameter and data files** (e.g. a params file or a CSV) supply the numeric
  values — use those values instead of guessing defaults.
- Do **not** invent compartments, parameters, or mechanisms from a run wrapper,
  entry-point, or config file that contains no dynamics.
- A **contact matrix** conveys the age/group structure of the model: declare it
  with `add_demographic_group` (age ranges). Its exact cell values are not
  transcribed — the schema uses built-in Prem 2021 contact matrices, with
  `set_contact_override` only for specific deviations that matter.
```

- [ ] **Step 4: Wire into `backend/prompt.py`**

Add near the other asset paths:
```python
_MULTI_FILE_FILE = _ASSETS / "multi_file_guidance.md"
```
Append in `build_system_prompt()` after the examples block:
```python
    multi_file = _strip_html_comments(_read(_MULTI_FILE_FILE))
    if multi_file:
        parts.append(multi_file)
```
Add to the `assets_status()` dict:
```python
        "multi_file_guidance_present": _MULTI_FILE_FILE.is_file()
        and bool(_strip_html_comments(_read(_MULTI_FILE_FILE))),
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/pytest tests/test_prompt.py -k multifile -v`
Expected: PASS.

---

### Task 3: Backend `files[]` handling + cap + health

**Files:**
- Modify: `backend/app.py`
- Test: `tests/test_app_multifile.py` (create)

**Interfaces:**
- Consumes: `render_source_files` (Task 1).
- Produces: `MAX_FILES`; `/api/health` `config.max_files`; `translate()` accepts
  `files` and falls back to `source_code`.

- [ ] **Step 1: Write failing tests**

`tests/test_app_multifile.py`:
```python
from fastapi.testclient import TestClient
from backend.app import app, MAX_FILES
from backend import translator

client = TestClient(app)

def _drain(resp):
    return resp.text

def test_health_includes_max_files():
    body = client.get("/api/health").json()
    assert body["config"]["max_files"] == MAX_FILES

def test_too_many_files_errors(monkeypatch):
    monkeypatch.setattr(translator, "api_key_present", lambda: True)
    files = [{"filename": f"f{i}.py", "content": "x"} for i in range(MAX_FILES + 1)]
    body = _drain(client.post("/api/translate", json={"files": files}))
    assert "Too many files" in body

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
    body = _drain(client.post("/api/translate", json={"files": files}))
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
    body = _drain(client.post("/api/translate", json={"source_code": "legacy"}))
    assert seen["src"] == "legacy"
    assert "OUT" in body
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/pytest tests/test_app_multifile.py -v`
Expected: FAIL (no MAX_FILES / max_files).

- [ ] **Step 3: Implement in `backend/app.py`**

Add import and constant:
```python
MAX_FILES = 10
```
In `health()`, add to the `config` — actually `config` comes from
`translator.config_summary()`; inject the cap alongside it:
```python
    config = translator.config_summary()
    config["max_files"] = MAX_FILES
    return {
        "status": "ok",
        "config": config,
        "assets": prompt_assets.assets_status(),
        "categories": categories_mod.public_categories(),
    }
```
In `translate()`, before building `event_stream`, resolve the source:
```python
    files = payload.get("files")
    too_many = isinstance(files, list) and len(files) > MAX_FILES
    if isinstance(files, list) and files:
        source_code = prompt_assets.render_source_files(files)
    else:
        source_code = (payload.get("source_code") or "").strip()
    source_language = (payload.get("source_language") or "").strip() or None
    category = (payload.get("category") or "").strip() or None
```
At the top of `event_stream()`, add the cap guard first:
```python
        if too_many:
            yield _sse({"error": f"Too many files (max {MAX_FILES})."})
            return
```
(`render_source_files` is exposed via `from backend import prompt as prompt_assets`,
already imported.)

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_app_multifile.py -v`
Expected: PASS.

---

### Task 4: Frontend file blocks + upload + cap

**Files:**
- Modify: `static/index.html`

No unit tests (vanilla JS SPA); verified live in Task 5.

- [ ] **Step 1: Replace the single source textarea with a file-block list**

In the source `<section class="pane">`, replace the `<textarea id="source">`
with a scrollable container plus a toolbar:
```html
      <div class="filebar">
        <button class="secondary mini" id="addFile">+ Add file</button>
        <label class="secondary mini" for="upload">Upload files</label>
        <input type="file" id="upload" multiple hidden />
        <span class="hint" id="fileHint" title="Include the model definition and the files with parameter values / initial conditions. Skip run scripts, plots, and tests. Export binary data (.rds/.mat/.npy) to text first. A contact matrix mainly conveys age structure.">what to include ⓘ</span>
      </div>
      <div id="files" class="files"></div>
```

- [ ] **Step 2: Add CSS** (near existing rules)

```css
  .filebar { display:flex; align-items:center; gap:8px; padding:8px 16px;
             border-bottom:1px solid var(--border); }
  .mini { padding:4px 10px; font-size:12px; font-weight:500; }
  .hint { color: var(--muted); font-size:12px; cursor:help; margin-left:auto; }
  .files { flex:1; overflow:auto; display:flex; flex-direction:column; min-height:0; }
  .fileblock { display:flex; flex-direction:column; border-bottom:1px solid var(--border); }
  .fileblock .fb-head { display:flex; gap:8px; align-items:center; padding:6px 16px; }
  .fileblock .fb-head input { flex:1; }
  .fileblock textarea { min-height:120px; }
  .fb-remove { background:transparent; border:0; color:var(--muted);
               cursor:pointer; font-size:16px; padding:0 6px; }
```

- [ ] **Step 3: Add JS block management** (replace `#source` usage)

```js
let MAX_FILES = 10;
function addFileBlock(filename = "", content = "") {
  const list = $("files");
  if (list.children.length >= MAX_FILES) return null;
  const block = document.createElement("div");
  block.className = "fileblock";
  block.innerHTML =
    `<div class="fb-head">` +
    `<input type="text" class="fb-name" placeholder="filename (optional)" />` +
    `<button class="fb-remove" title="Remove">×</button></div>` +
    `<textarea class="fb-content" placeholder="Paste model source or parameter/data here…" spellcheck="false"></textarea>`;
  block.querySelector(".fb-name").value = filename;
  block.querySelector(".fb-content").value = content;
  block.querySelector(".fb-remove").addEventListener("click", () => {
    block.remove();
    if ($("files").children.length === 0) addFileBlock();
    refreshAddState();
  });
  block.querySelector(".fb-content").addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") translate();
  });
  list.appendChild(block);
  refreshAddState();
  return block;
}
function refreshAddState() {
  $("addFile").disabled = $("files").children.length >= MAX_FILES;
}
function collectFiles() {
  return [...$("files").children].map((b) => ({
    filename: b.querySelector(".fb-name").value.trim(),
    content: b.querySelector(".fb-content").value,
  })).filter((f) => f.content.trim());
}
$("addFile").addEventListener("click", () => addFileBlock());
$("upload").addEventListener("change", (e) => {
  const files = [...e.target.files];
  const free = MAX_FILES - $("files").children.length;
  let skipped = 0;
  files.forEach((file, i) => {
    if (i >= free) { skipped++; return; }
    const reader = new FileReader();
    reader.onload = () => addFileBlock(file.name, reader.result);
    reader.readAsText(file);
  });
  if (skipped) setStatus(`skipped ${skipped} (max ${MAX_FILES})`, true);
  e.target.value = "";
});
addFileBlock();
```

- [ ] **Step 4: Update `translate()` and `loadConfig()`**

In `translate()`:
```js
  const files = collectFiles();
  if (!files.length) { setStatus("Paste or upload some source first.", true); return; }
  ...
      body: JSON.stringify({
        files,
        source_language: $("lang").value.trim(),
        category: $("category").value,
      }),
```
In `loadConfig()`, after reading config:
```js
    if (typeof c.max_files === "number") { MAX_FILES = c.max_files; refreshAddState(); }
```

- [ ] **Step 5: Manual check** — page loads with one empty block; Add/Upload
  work; cap disables Add at 10.

---

### Task 5: Docs + end-to-end verification

**Files:**
- Modify: `docs/prompt-change-log.md`, `docs/ROADMAP.md`, `README.md`

- [ ] **Step 1: Log the prompt change** in `docs/prompt-change-log.md`
  (new appended `multi_file_guidance.md`, purpose + rationale).
- [ ] **Step 2: ROADMAP** — mark #2 shipped; single-file output kept; multi-file
  output still deferred.
- [ ] **Step 3: README** — note multi-file submission (upload or paste),
  headers, single `model.py` out, include/skip guidance.
- [ ] **Step 4: Full suite** — `.venv/bin/pytest -q` (all green).
- [ ] **Step 5: Live check** — start uvicorn, load UI, submit two files, confirm
  headered source reaches the translation and a `model.py` streams back.
- [ ] **Step 6: Update project docs / CLAUDE.md** if the prompt-assembly story
  changed (it adds one appended file) — one line if needed.
