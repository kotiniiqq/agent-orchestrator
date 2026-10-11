import pytest

from orchestrator.jsonout import DICTS, STRS, InvalidOutput, extract_object, parse

REVIEW = {"agree": bool, "objections": STRS, "proposed_change": str}


def test_plain_object():
    assert extract_object('{"a": 1}') == {"a": 1}


def test_code_fence_and_prose():
    text = 'Sure, here it is:\n```json\n{"agree": true, "objections": [], "proposed_change": ""}\n```\nThanks.'
    assert parse(text, REVIEW)["agree"] is True


def test_braces_inside_strings():
    text = 'note {"position": "use {curly} and \\"quotes\\"", "reasons": ["a}b"]} trailing }'
    assert extract_object(text)["position"] == 'use {curly} and "quotes"'


def test_first_valid_object_wins():
    assert extract_object('{not json} then {"a": 2}') == {"a": 2}


@pytest.mark.parametrize(
    "text",
    [
        "",
        "no json here",
        '{"agree": "yes", "objections": [], "proposed_change": ""}',
        '{"agree": true, "objections": "none", "proposed_change": ""}',
        '{"agree": true, "objections": [1, 2], "proposed_change": ""}',
        '{"agree": true, "objections": []}',
        '["a list"]',
        '{"agree": true, "objections": [{"x": 1}], "proposed_change": ""}',
    ],
)
def test_invalid(text):
    with pytest.raises(InvalidOutput):
        parse(text, REVIEW)


def test_extra_keys_are_dropped():
    out = parse('{"agree": false, "objections": ["x"], "proposed_change": "y", "mood": "grumpy"}', REVIEW)
    assert out == {"agree": False, "objections": ["x"], "proposed_change": "y"}


def test_list_of_objects():
    out = parse('{"rulings": [{"objection": "a", "decision": "accepted", "reason": "r"}]}', {"rulings": DICTS})
    assert out["rulings"][0]["decision"] == "accepted"
    with pytest.raises(InvalidOutput):
        parse('{"rulings": ["a"]}', {"rulings": DICTS})
