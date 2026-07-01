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
