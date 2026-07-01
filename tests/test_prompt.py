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
