"""
Assembles the translation prompt from the editable files in ``prompt_assets/``.

The whole point of keeping this in plain files is that you can drop your real
prompt, schema, and examples in without touching Python:

    prompt_assets/system_prompt.md   -> translation instructions
    prompt_assets/target_schema.py   -> the Python target schema
    prompt_assets/examples/<name>/   -> before/after worked example pairs
        source.<ext> + target.py

The system prompt is the *stable* part of every request (instructions + schema +
examples), so it is cached on the API side — repeat translations only pay for
the source code you paste in. See build_system_prompt() / build_user_message().
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

from backend.categories import hint_for

# prompt_assets/ lives next to the repo root (one level up from backend/).
_ASSETS = Path(__file__).resolve().parent.parent / "prompt_assets"
_SYSTEM_PROMPT_FILE = _ASSETS / "system_prompt.md"
_SCHEMA_FILE = _ASSETS / "target_schema.py"
_OUTPUT_REPORT_FILE = _ASSETS / "output_report.md"
_MULTI_FILE_FILE = _ASSETS / "multi_file_guidance.md"
_EXAMPLES_DIR = _ASSETS / "examples"

# Map common source-model file extensions to a human-readable language name,
# used only to label example sources and (optionally) the pasted source.
_EXT_TO_LANG = {
    ".r": "R",
    ".jl": "Julia",
    ".m": "MATLAB",
    ".py": "Python",
    ".cpp": "C++",
    ".cc": "C++",
    ".c": "C",
    ".java": "Java",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".f": "Fortran",
    ".f90": "Fortran",
    ".stan": "Stan",
}


def _strip_html_comments(text: str) -> str:
    """Remove <!-- ... --> blocks (used for editor guidance in the md file)."""
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL).strip()


def language_for_extension(ext: str) -> str:
    return _EXT_TO_LANG.get(ext.lower(), ext.lstrip(".").upper() or "unknown")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _load_examples() -> List[Tuple[str, str, str]]:
    """Return [(example_name, source_language, formatted_text), ...].

    Each example subdirectory pairs a ``source.<ext>`` file with ``target.py``.
    """
    examples: List[Tuple[str, str, str]] = []
    if not _EXAMPLES_DIR.is_dir():
        return examples

    for sub in sorted(p for p in _EXAMPLES_DIR.iterdir() if p.is_dir()):
        target = sub / "target.py"
        sources = sorted(
            p for p in sub.glob("source.*") if p.is_file()
        )
        if not target.is_file() or not sources:
            continue
        source = sources[0]
        lang = language_for_extension(source.suffix)
        source_code = _read(source).rstrip()
        target_code = _read(target).rstrip()
        if not source_code or not target_code:
            continue

        block = (
            f"### Example: {sub.name}\n\n"
            f"Source model ({lang}):\n"
            f"```\n{source_code}\n```\n\n"
            f"Correct translation into the target schema:\n"
            f"```python\n{target_code}\n```"
        )
        examples.append((sub.name, lang, block))
    return examples


def build_system_prompt() -> str:
    """Assemble the full system prompt: instructions + schema + worked examples."""
    instructions = _strip_html_comments(_read(_SYSTEM_PROMPT_FILE))

    parts: List[str] = [instructions]

    schema = _read(_SCHEMA_FILE).rstrip()
    if schema:
        parts.append(
            "## TARGET SCHEMA\n\n"
            "The translated code MUST conform to this schema:\n\n"
            f"```python\n{schema}\n```"
        )

    examples = _load_examples()
    if examples:
        rendered = "\n\n".join(block for _, _, block in examples)
        parts.append("## WORKED EXAMPLES\n\n" + rendered)

    multi_file = _strip_html_comments(_read(_MULTI_FILE_FILE))
    if multi_file:
        parts.append(multi_file)

    return "\n\n".join(p for p in parts if p).strip()


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


def render_source_files(files: List[dict]) -> str:
    """Concatenate submitted files into one source string.

    Each file is ``{"filename": str, "content": str}``. Blank-content files are
    dropped. A single file with no filename is returned verbatim (byte-identical
    to a plain single paste, so the prompt cache and example framing are
    preserved). Otherwise each file is emitted under a
    ``=== file: <name> (<Lang>) ===`` header, in the given order.
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


# --- Translation report (separate structured call) --------------------------
# The report is produced by a SECOND model call that reads the source + the
# generated model.py and returns a structured JSON object (schema-enforced).
# This keeps the report entirely out of the code stream — the code call above
# stays "bare model.py only".

def build_report_system_prompt() -> str:
    """Instructions for the report call: how to classify the translation."""
    return _strip_html_comments(_read(_OUTPUT_REPORT_FILE))


def build_report_user_message(
    source_code: str,
    model_code: str,
    source_language: str | None = None,
) -> str:
    """Build the report call's user turn: the source and the translated model.py."""
    lang = (source_language or "").strip()
    lang_note = f" (source language: {lang})" if lang else ""
    return (
        f"SOURCE MODEL{lang_note}:\n\n```\n{source_code.rstrip()}\n```\n\n"
        "TRANSLATED model.py:\n\n"
        f"```python\n{model_code.rstrip()}\n```\n\n"
        "Produce the translation report as a JSON object per the instructions."
    )


def assets_status() -> dict:
    """Lightweight introspection for the /api/health endpoint and the UI."""
    examples = _load_examples()
    return {
        "system_prompt_present": _SYSTEM_PROMPT_FILE.is_file()
        and bool(_strip_html_comments(_read(_SYSTEM_PROMPT_FILE))),
        "schema_present": _SCHEMA_FILE.is_file() and bool(_read(_SCHEMA_FILE).strip()),
        "example_count": len(examples),
        "example_names": [name for name, _, _ in examples],
        "output_report_present": _OUTPUT_REPORT_FILE.is_file()
        and bool(_strip_html_comments(_read(_OUTPUT_REPORT_FILE))),
        "multi_file_guidance_present": _MULTI_FILE_FILE.is_file()
        and bool(_strip_html_comments(_read(_MULTI_FILE_FILE))),
    }
