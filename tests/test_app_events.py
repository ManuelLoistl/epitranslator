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
