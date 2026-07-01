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

# prompt_assets/ lives next to the repo root (one level up from backend/).
_ASSETS = Path(__file__).resolve().parent.parent / "prompt_assets"
_SYSTEM_PROMPT_FILE = _ASSETS / "system_prompt.md"
_SCHEMA_FILE = _ASSETS / "target_schema.py"
_OUTPUT_REPORT_FILE = _ASSETS / "output_report.md"
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

    report_instr = _strip_html_comments(_read(_OUTPUT_REPORT_FILE))
    if report_instr:
        parts.append(report_instr)

    return "\n\n".join(p for p in parts if p).strip()


def build_user_message(source_code: str, source_language: str | None = None) -> str:
    """Build the user turn: the source model to translate."""
    lang = (source_language or "").strip()
    header = (
        f"Translate the following disease model"
        + (f" (source language: {lang})" if lang else "")
        + " into the target schema. Output only the bare translated Python code."
    )
    return f"{header}\n\n```\n{source_code.rstrip()}\n```"


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
    }
