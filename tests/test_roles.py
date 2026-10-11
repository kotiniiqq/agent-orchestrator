import pytest

from orchestrator.roles import RolesError, load_roles

GOOD = """
roles:
  - id: architect
    job: proposes a concrete solution
    model: a/m1
  - id: critic
    job: finds risks
    model: b/m2
  - id: moderator
    job: merges and rules
    model: a/m1
    moderator: true
"""


def write(tmp_path, text):
    p = tmp_path / "roles.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_loads_participants_and_moderator(tmp_path):
    roles = load_roles(write(tmp_path, GOOD))
    assert [r.id for r in roles.participants] == ["architect", "critic"]
    assert roles.moderator.id == "moderator"
    assert roles.participants[1].model == "b/m2"


@pytest.mark.parametrize(
    "text, message",
    [
        (GOOD.replace("    moderator: true\n", ""), "exactly one moderator"),
        (GOOD + "  - id: m2\n    job: x\n    model: c\n    moderator: true\n", "exactly one moderator"),
        (GOOD.replace("  - id: critic\n    job: finds risks\n    model: b/m2\n", ""), "at least 2 participants"),
        (GOOD.replace("id: critic", "id: architect"), "duplicate role id"),
        (GOOD.replace("    model: b/m2\n", ""), "critic: model"),
        ("roles: nope", "list of roles"),
    ],
)
def test_validation(tmp_path, text, message):
    with pytest.raises(RolesError, match=message):
        load_roles(write(tmp_path, text))


def test_default_roles_file_is_valid():
    roles = load_roles("roles.yaml")
    assert [r.id for r in roles.participants] == ["architect", "critic", "pragmatist"]
