"""Regression tests for _strip_code_fences.

The tricky requirement: strip a wrapping ```lang / ``` fence pair, but NEVER
drop a ``` line that is real code (which happens when the model emits bare code
whose last line is a lone ``` — e.g. the end of a docstring, or a stream
truncated mid-string).
"""
from backend.translator import _strip_code_fences


def strip(text: str) -> str:
    """Run the streaming stripper over `text` as a single chunk."""
    return "".join(_strip_code_fences(iter([text])))


def test_bare_code_ending_in_triple_backtick_is_preserved():
    # No opening fence was consumed, so the trailing ``` is real code.
    assert strip("x = 1\n```\n") == "x = 1\n```\n"


def test_wrapped_code_strips_both_fences():
    assert strip("```python\nx = 1\n```\n") == "x = 1\n"


def test_bare_code_unchanged():
    src = "def f():\n    return 1\n"
    assert strip(src) == src


def test_triple_backtick_inside_body_is_preserved():
    src = 'D = """\n```\n"""\n'
    assert strip(src) == src


def test_opening_fence_only_is_dropped():
    # Opening fence consumed, no closing fence: emit the body as-is.
    assert strip("```python\nx = 1\n") == "x = 1\n"


def test_wrapped_code_without_trailing_newline():
    # Closing fence is the final partial line (no trailing "\n").
    assert strip("```python\nx = 1\n```") == "x = 1\n"


def test_bare_code_final_backtick_without_trailing_newline():
    assert strip("x = 1\n```") == "x = 1\n```"


def test_empty_stream():
    assert strip("") == ""


def test_fence_split_across_chunks():
    chunks = ["``", "`py", "thon\nx = 1\n``", "`\n"]
    assert "".join(_strip_code_fences(iter(chunks))) == "x = 1\n"
