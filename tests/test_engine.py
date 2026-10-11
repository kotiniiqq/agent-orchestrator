import asyncio
import json
import time

import pytest

from orchestrator import prompts
from orchestrator.engine import Deliberation, QuestionError, validate_question
from orchestrator.llm import Completion, LLMError
from orchestrator.roles import Role, Roles

ROLES = Roles(
    participants=[Role("architect", "j", "m/a"), Role("critic", "j", "m/c"), Role("pragmatist", "j", "m/p")],
    moderator=Role("moderator", "j", "m/mod", moderator=True),
)


def j(obj) -> str:
    return json.dumps(obj)


AGREE = j({"agree": True, "objections": [], "proposed_change": ""})


def objects(text):
    return j({"agree": False, "objections": [text], "proposed_change": "change it"})


class Script:
    """Replies per (role, phase); a list is consumed in order, its last item repeats."""

    def __init__(self, replies=None, delay=0.0):
        self.replies = {
            ("architect", "proposal"): [j({"position": "A", "reasons": ["ra"]})],
            ("critic", "proposal"): [j({"position": "C", "reasons": ["rc"]})],
            ("pragmatist", "proposal"): [j({"position": "P", "reasons": ["rp"]})],
            ("moderator", "draft"): [j({"draft": "D1"})],
            ("architect", "review"): [AGREE],
            ("critic", "review"): [AGREE],
            ("pragmatist", "review"): [AGREE],
            ("moderator", "revise"): [j({"draft": "D2", "rulings": [{"objection": "x", "decision": "accepted", "reason": "fair"}]})],
            ("moderator", "final"): [j({"decision": "FINAL", "reasons": ["r1", "r2"]})],
        }
        self.replies.update(replies or {})
        self.calls = []
        self.delay = delay

    async def complete(self, model, system, user):
        role, phase = prompts.marker(system, "role"), prompts.marker(user, "phase")
        self.calls.append((role, phase, user))
        if self.delay:
            await asyncio.sleep(self.delay)
        queue = self.replies[(role, phase)]
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, float):  # sleep that long, then agree
            await asyncio.sleep(item)
            return Completion(AGREE)
        return Completion(item, tokens_in=10, tokens_out=5, usd=0.001)


async def run(script, **kw):
    return await Deliberation(script, ROLES, **kw).run("Should we cache the reports?")


async def test_consensus_in_the_first_round():
    s = Script()
    r = await run(s)
    assert r.consensus and r.rounds == 1 and r.decision == "FINAL" and r.reasons == ["r1", "r2"]
    assert r.dissent == {} and r.warnings == []
    assert not any(phase == "revise" for _, phase, _ in s.calls)


async def test_accepted_objection_leads_to_consensus_in_round_two():
    s = Script({("critic", "review"): [objects("no metric"), AGREE]})
    r = await run(s)
    assert r.consensus and r.rounds == 2
    assert r.rulings == [{"objection": "x", "decision": "accepted", "reason": "fair"}]
    second_review = [u for role, phase, u in s.calls if role == "architect" and phase == "review"][1]
    assert "D2" in second_review  # the revised draft is what gets reviewed


async def test_round_limit_keeps_dissent():
    s = Script({("pragmatist", "review"): [objects("too big")]})
    r = await run(s, max_rounds=3)
    assert not r.consensus and r.rounds == 3
    assert r.dissent == {"pragmatist": ["too big"]}
    assert sum(1 for _, p, _ in s.calls if p == "revise") == 2  # no revision after the last round


async def test_invalid_json_is_retried_once():
    s = Script({("critic", "review"): ["I agree!", AGREE]})
    r = await run(s)
    assert r.consensus and r.warnings == []
    retry = [u for role, p, u in s.calls if role == "critic" and p == "review"][1]
    assert "not valid JSON" in retry


async def test_second_invalid_reply_is_an_abstention():
    s = Script({("critic", "review"): ["nope", "still nope", AGREE]})
    r = await run(s)
    assert any("critic" in w and "abstained" in w for w in r.warnings)
    assert r.consensus and r.rounds == 2  # an abstention blocks consensus in that round


async def test_agent_failing_twice_becomes_inactive():
    s = Script({("pragmatist", "review"): [LLMError(429, "rate limited")]})
    r = await run(s, max_rounds=4)
    assert r.consensus and r.rounds == 2  # second failure in round 2: inactive, the other two decide
    assert any("pragmatist" in w and "inactive" in w for w in r.warnings)


async def test_timeout_counts_as_a_failure():
    s = Script({("pragmatist", "review"): [5.0]})
    r = await run(s, timeout=0.05)
    assert any("pragmatist" in w and "did not answer" in w for w in r.warnings)


async def test_quorum_lost():
    err = LLMError(500, "down")
    s = Script({("critic", "review"): [err], ("pragmatist", "review"): [err]})
    r = await run(s, max_rounds=4)
    assert not r.consensus
    assert any("quorum" in w for w in r.warnings)


async def test_moderator_failure_keeps_the_last_draft():
    s = Script({("critic", "review"): [objects("no metric")], ("moderator", "revise"): [LLMError(500, "down")]})
    r = await run(s)
    assert not r.consensus and r.decision == "D1" and r.error
    assert r.dissent == {"critic": ["no metric"]}


async def test_final_failure_falls_back_to_the_draft():
    s = Script({("moderator", "final"): [LLMError(500, "down")]})
    r = await run(s)
    assert r.consensus and r.decision == "D1" and r.reasons == []
    assert any("final" in w for w in r.warnings)


async def test_proposals_and_reviews_run_in_parallel():
    s = Script(delay=0.1)
    start = time.monotonic()
    await run(s)
    # sequential would be 3 + 1 + 3 + 1 = 8 calls x 0.1 s
    assert time.monotonic() - start < 0.55


async def test_usage_is_summed_per_role():
    r = await run(Script())
    assert r.usage.calls == 8 and r.usage.tokens_in == 80 and round(r.usage.usd, 6) == 0.008
    assert r.usage.by_role["moderator"]["calls"] == 2


async def test_events_report_progress():
    events = []
    await Deliberation(Script({("critic", "review"): [objects("x"), AGREE]}), ROLES, on_event=events.append).run("q? yes")
    assert ("round", 1) in events and ("round", 2) in events
    assert ("done", "critic", "review") in events


async def test_transcript_has_every_step():
    r = await run(Script({("critic", "review"): [objects("x"), AGREE]}))
    steps = [(e.round, e.role, e.phase) for e in r.transcript]
    assert (0, "architect", "proposal") in steps and (0, "moderator", "draft") in steps
    assert (1, "moderator", "revise") in steps and (2, "pragmatist", "review") in steps
    assert steps[-1] == (2, "moderator", "final")


@pytest.mark.parametrize("q", ["", "  ", "ab", "x" * 2001])
def test_question_limits(q):
    with pytest.raises(QuestionError):
        validate_question(q)


def test_question_is_trimmed():
    assert validate_question("  why?  ") == "why?"


async def test_demo_client_plays_all_three_scenarios():
    from orchestrator.llm import DemoClient, scenario
    from orchestrator.roles import load_roles

    roles = load_roles("roles.yaml")
    seen = {}
    for i in range(30):
        q = f"Should we move the reports to a queue? #{i}"
        seen.setdefault(scenario(q), await Deliberation(DemoClient(), roles).run(q))
    assert seen[0].consensus and seen[0].rounds == 1
    assert seen[1].consensus and seen[1].rounds == 2 and seen[1].rulings[0]["decision"] == "accepted"
    assert not seen[2].consensus and seen[2].rounds == 4 and list(seen[2].dissent) == ["pragmatist"]
    assert all(r.warnings == [] for r in seen.values())


async def test_repeated_rulings_are_kept_once():
    s = Script({("pragmatist", "review"): [objects("too big")]})
    r = await run(s, max_rounds=4)
    assert r.rulings == [{"objection": "x", "decision": "accepted", "reason": "fair"}]
