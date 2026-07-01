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
