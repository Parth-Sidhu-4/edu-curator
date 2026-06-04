from edu_curator.extraction import parse_json_robust


def test_parse_json_robust_valid():
    valid_json = '{"key": "value"}'
    result = parse_json_robust(valid_json)
    assert result == {"key": "value"}


def test_parse_json_robust_malformed():
    # Missing closing brace
    malformed_json = '{"key": "value"'
    # This will fail standard json.loads but json_repair should fix it
    result = parse_json_robust(malformed_json)
    assert result == {"key": "value"}


def test_parse_json_robust_trailing_comma():
    # Trailing comma
    malformed_json = '{"key": "value",}'
    result = parse_json_robust(malformed_json)
    assert result == {"key": "value"}


def test_parse_json_robust_markdown_blocks():
    # Markdown formatting common from LLMs
    malformed_json = '```json\n{"key": "value"}\n```'
    result = parse_json_robust(malformed_json)
    assert result == {"key": "value"}
