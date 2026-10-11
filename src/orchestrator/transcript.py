"""What a debate produces: the result and the record of every step."""

from dataclasses import dataclass, field


@dataclass
class Usage:
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    usd: float = 0.0
    by_role: dict[str, dict] = field(default_factory=dict)

    def add(self, role: str, tokens_in: int, tokens_out: int, usd: float) -> None:
        self.calls += 1
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        self.usd += usd
        r = self.by_role.setdefault(role, {"calls": 0, "tokens_in": 0, "tokens_out": 0, "usd": 0.0})
        r["calls"] += 1
        r["tokens_in"] += tokens_in
        r["tokens_out"] += tokens_out
        r["usd"] += usd


@dataclass
class Entry:
    round: int  # 0 = proposals and first draft
    role: str
    phase: str
    payload: dict | None  # the parsed reply; None if the agent abstained
    warning: str | None = None


@dataclass
class Result:
    question: str
    decision: str
    reasons: list[str]
    dissent: dict[str, list[str]]  # role -> objections still open at the end
    consensus: bool
    rounds: int
    usage: Usage
    warnings: list[str]
    transcript: list[Entry]
    rulings: list[dict] = field(default_factory=list)
    error: str | None = None
