"""Pull a JSON object out of a model reply and check its shape.

Models wrap JSON in prose or code fences; this finds the first balanced
object that parses, then checks required keys and types.
"""

import json


class InvalidOutput(ValueError):
    pass


STRS = (list, str)  # a list of strings
DICTS = (list, dict)  # a list of objects


def _candidates(text: str):
    for start, ch in enumerate(text):
        if ch != "{":
            continue
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    yield text[start : i + 1]
                    break


def extract_object(text: str) -> dict:
    for cand in _candidates(text or ""):
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise InvalidOutput("no JSON object in the reply")


def parse(text: str, schema: dict[str, type | tuple[type, type]]) -> dict:
    """Return only the schema's keys. A schema value is a type, or STRS / DICTS for lists."""
    obj = extract_object(text)
    out = {}
    for key, typ in schema.items():
        if key not in obj:
            raise InvalidOutput(f"missing key {key!r}")
        val = obj[key]
        if isinstance(typ, tuple):
            item = typ[1]
            if not isinstance(val, list) or not all(isinstance(x, item) for x in val):
                raise InvalidOutput(f"{key!r} must be a list of {'strings' if item is str else 'objects'}")
        elif not isinstance(val, typ):
            raise InvalidOutput(f"{key!r} must be {'true or false' if typ is bool else typ.__name__}")
        out[key] = val
    return out
