from backend.report import SENTINEL, split_stream, parse_report


def collect(chunks):
    return list(split_stream(chunks))


def test_no_sentinel_streams_all_text():
    assert collect(["import x\n", "y = 1\n"]) == [
        ("text", "import x\n"),
        ("text", "y = 1\n"),
    ]


def test_no_sentinel_no_trailing_newline_flushes_tail():
    assert collect(["a\n", "b"]) == [("text", "a\n"), ("text", "b")]


def test_sentinel_splits_code_from_report():
    out = collect(["code\n", SENTINEL + "\n", '{"a": 1}'])
    assert out == [("text", "code\n"), ("report", '{"a": 1}')]


def test_sentinel_split_across_chunks():
    out = collect(["code\n# ---TRANSLATION", "-REPORT---\n", "{}"])
    assert out == [("text", "code\n"), ("report", "{}")]


def test_report_accumulates_across_chunks():
    out = collect(["c\n", SENTINEL + "\n", '{"a":', "1}"])
    assert out == [("text", "c\n"), ("report", '{"a":1}')]


def test_parse_report_valid():
    assert parse_report('{"a": 1}') == {"a": 1}


def test_parse_report_malformed_returns_none():
    assert parse_report("{not json") is None


def test_parse_report_empty_returns_none():
    assert parse_report("   ") is None


def test_parse_report_non_object_returns_none():
    assert parse_report("[1, 2]") is None


def test_tolerant_sentinel_paraphrased_divider():
    # Model paraphrased the sentinel (=== and a space); it must still split out.
    out = collect(["code\n", "# ===TRANSLATION REPORT===\n", '{"a": 1}'])
    assert out == [("text", "code\n"), ("report", '{"a": 1}')]


def test_tolerant_sentinel_variants_all_detected():
    for line in [
        "# ---TRANSLATION-REPORT---",
        "# ===TRANSLATION REPORT===",
        "#===TRANSLATION_REPORT===",
        "  ## -- translation-report --  ",
    ]:
        out = collect(["c\n", line + "\n", "{}"])
        assert out == [("text", "c\n"), ("report", "{}")], line


def test_non_sentinel_comment_not_matched():
    # An ordinary comment must NOT be treated as the sentinel.
    out = collect(["# regular comment\n", "x = 1\n"])
    assert out == [("text", "# regular comment\n"), ("text", "x = 1\n")]


def test_parse_report_fallback_extracts_outermost_braces():
    assert parse_report('noise before {"a": 1} noise after') == {"a": 1}


def test_parse_report_fallback_strips_code_fence():
    assert parse_report('```json\n{"a": 1}\n```') == {"a": 1}
