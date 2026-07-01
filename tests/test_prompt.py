from backend.prompt import (
    build_system_prompt,
    build_report_system_prompt,
    build_report_user_message,
    assets_status,
)
from backend import translator


def test_code_prompt_is_pure_code_only():
    # The translation (code) prompt must NOT mention the report — the report is a
    # separate call, and the code call stays "bare model.py only".
    prompt = build_system_prompt().lower()
    assert "translation-report" not in prompt
    assert "translation report" not in prompt
    assert "output **only**" in prompt or "output only" in prompt


def test_report_system_prompt_present():
    text = build_report_system_prompt()
    assert "translation report" in text.lower()
    assert "origin" in text.lower()


def test_report_user_message_includes_source_and_model():
    msg = build_report_user_message("SRC_CODE_HERE", "MODEL_PY_HERE", "R")
    assert "SRC_CODE_HERE" in msg
    assert "MODEL_PY_HERE" in msg
    assert "source language: R" in msg


def test_assets_status_reports_output_report_present():
    assert assets_status()["output_report_present"] is True


def test_report_schema_shape():
    schema = translator.REPORT_SCHEMA
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "attention",
        "compartments",
        "parameters",
        "interventions",
    }


def test_generate_report_none_on_empty_code():
    # No model.py -> no report, and no API call is made.
    assert translator.generate_report("some source", "") is None


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


def test_health_includes_categories():
    from fastapi.testclient import TestClient
    from backend.app import app
    r = TestClient(app).get("/api/health")
    body = r.json()
    assert "categories" in body
    assert body["categories"][0] == {"id": "unspecified", "label": "Unspecified"}


# --- render_source_files -----------------------------------------------------

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


# --- appended multi-file guidance -------------------------------------------

def test_system_prompt_includes_multifile_guidance():
    p = build_system_prompt().lower()
    assert "several files" in p or "multiple files" in p


def test_assets_status_reports_multifile_present():
    assert assets_status()["multi_file_guidance_present"] is True
