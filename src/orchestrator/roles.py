"""Roles of a debate, loaded from roles.yaml."""

from dataclasses import dataclass
from pathlib import Path

import yaml


class RolesError(ValueError):
    pass


@dataclass(frozen=True)
class Role:
    id: str
    job: str
    model: str
    moderator: bool = False


@dataclass(frozen=True)
class Roles:
    participants: list[Role]
    moderator: Role

    def by_id(self, role_id: str) -> Role:
        for r in [*self.participants, self.moderator]:
            if r.id == role_id:
                return r
        raise KeyError(role_id)


def load_roles(path: str | Path) -> Roles:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    items = data.get("roles") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise RolesError(f"{path}: expected a list of roles under 'roles'")
    roles, seen = [], set()
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise RolesError(f"{path}: role #{i + 1} must be a mapping")
        rid = str(item.get("id") or "").strip()
        if not rid:
            raise RolesError(f"{path}: role #{i + 1}: id is required")
        if rid in seen:
            raise RolesError(f"{path}: duplicate role id {rid!r}")
        seen.add(rid)
        for key in ("job", "model"):
            if not str(item.get(key) or "").strip():
                raise RolesError(f"{path}: {rid}: {key} is required")
        roles.append(Role(rid, str(item["job"]).strip(), str(item["model"]).strip(), bool(item.get("moderator", False))))
    moderators = [r for r in roles if r.moderator]
    if len(moderators) != 1:
        raise RolesError(f"{path}: need exactly one moderator, found {len(moderators)}")
    participants = [r for r in roles if not r.moderator]
    if len(participants) < 2:
        raise RolesError(f"{path}: need at least 2 participants, found {len(participants)}")
    return Roles(participants, moderators[0])
