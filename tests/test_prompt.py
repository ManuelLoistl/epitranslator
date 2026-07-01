from backend.prompt import build_system_prompt, assets_status
from backend.report import SENTINEL


def test_system_prompt_includes_report_instruction():
    prompt = build_system_prompt()
    assert SENTINEL in prompt
    assert "translation report" in prompt.lower()


def test_assets_status_reports_output_report_present():
    status = assets_status()
    assert status["output_report_present"] is True


def test_user_message_does_not_forbid_the_report():
    from backend.prompt import build_user_message
    msg = build_user_message("print(1)")
    assert "only the bare" not in msg.lower()
