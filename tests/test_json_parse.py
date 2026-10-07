import pytest

from llm.json_parse import extract_json_object


def test_plain_json():
    assert extract_json_object('{"goal": "x"}') == {"goal": "x"}


def test_fenced_json_block():
    assert extract_json_object('```json\n{"goal": "x"}\n```') == {"goal": "x"}


def test_json_with_surrounding_text():
    assert extract_json_object('说明：\n{"goal": "x"}\n以上') == {"goal": "x"}


def test_trailing_comma_is_repaired():
    assert extract_json_object('{"a": 1, "b": 2,}') == {"a": 1, "b": 2}


def test_non_dict_is_rejected():
    with pytest.raises(ValueError):
        extract_json_object('[1, 2, 3]')


def test_garbage_is_rejected():
    with pytest.raises(ValueError):
        extract_json_object('完全没有 JSON')
