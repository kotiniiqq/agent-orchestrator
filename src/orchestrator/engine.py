"""The debate: proposals, a merged draft, then review rounds until everyone agrees.

Participants vote; the moderator merges, rules on objections and writes the
final answer. Disagreement is never averaged away: an objection is either
accepted (and the draft changes), rejected with a reason, or still open at the
end and reported as dissent.
"""

import asyncio
import inspect
from collections.abc import Callable

from . import prompts
from .jsonout import DICTS, STRS, InvalidOutput, parse
from .llm import LLM, LLMError
from .roles import Role, Roles
from .transcript import Entry, Result, Usage

MIN_QUESTION, MAX_QUESTION = 3, 2000
QUORUM = 2

PROPOSAL_SCHEMA = {"position": str, "reasons": STRS}
DRAFT_SCHEMA = {"draft": str}
REVIEW_SCHEMA = {"agree": bool, "objections": STRS, "proposed_change": str}
REVISE_SCHEMA = {"draft": str, "rulings": DICTS}
FINAL_SCHEMA = {"decision": str, "reasons": STRS}


class QuestionError(ValueError):
    pass


def validate_question(q: str) -> str:
    q = (q or "").strip()
    if not MIN_QUESTION <= len(q) <= MAX_QUESTION:
        raise QuestionError(f"A question must be {MIN_QUESTION} to {MAX_QUESTION} characters.")
    return q


class _Failed(Exception):
    pass


class Deliberation:
    def __init__(self, llm: LLM, roles: Roles, max_rounds: int = 4, timeout: float = 60.0, on_event: Callable | None = None):
        self.llm = llm
        self.roles = roles
        self.max_rounds = max_rounds
        self.timeout = timeout
        self.on_event = on_event

    async def _emit(self, *event) -> None:
        if self.on_event:
            res = self.on_event(event)
            if inspect.isawaitable(res):
                await res

    async def _ask(self, role: Role, phase: str, user: str, schema: dict, rnd: int, st: "_State") -> dict:
        """One agent call with one retry on invalid JSON. Raises _Failed after recording why."""
        system = prompts.system_prompt(role.id, role.job, role.moderator)
        prompt = user
        why = ""
        for attempt in (1, 2):
            try:
                c = await asyncio.wait_for(self.llm.complete(role.model, system, prompt), self.timeout)
            except TimeoutError:
                why = f"did not answer within {self.timeout:g} s"
                break
            except LLMError as e:
                why = str(e)
                break
            st.usage.add(role.id, c.tokens_in, c.tokens_out, c.usd)
            try:
                out = parse(c.text, schema)
            except InvalidOutput as e:
                why = f"invalid reply ({e})"
                prompt = f"{user}\n\nYour previous reply was not valid JSON for this format: {e}. Reply with the JSON object only."
                continue
            st.transcript.append(Entry(rnd, role.id, phase, out))
            await self._emit("done", role.id, phase)
            return out
        warning = f"{role.id} abstained in {phase} (round {rnd}): {why}"
        st.transcript.append(Entry(rnd, role.id, phase, None, warning))
        st.warnings.append(warning)
        await self._emit("done", role.id, phase)
        raise _Failed(why)

    async def run(self, question: str) -> Result:
        q = validate_question(question)
        st = _State()
        mod = self.roles.moderator
        active = [p.id for p in self.roles.participants]
        fails = dict.fromkeys(active, 0)

        async def gather(phase, make_prompt, schema, rnd):
            ids = list(active)
            outs = await asyncio.gather(
                *(self._ask(self.roles.by_id(r), phase, make_prompt(r), schema, rnd, st) for r in ids),
                return_exceptions=True,
            )
            got = {}
            for r, out in zip(ids, outs):
                if isinstance(out, _Failed):
                    fails[r] += 1
                    if fails[r] >= 2:
                        active.remove(r)
                        st.warnings.append(f"{r} is inactive after two failed turns in a row")
                elif isinstance(out, BaseException):
                    raise out
                else:
                    fails[r] = 0
                    got[r] = out
            return got

        def result(draft, consensus, rounds, dissent, error=None, decision=None, reasons=None):
            return Result(q, decision if decision is not None else draft, reasons or [], dissent, consensus, rounds,
                          st.usage, st.warnings, st.transcript, st.rulings, error)

        await self._emit("round", 0)
        proposals = await gather(prompts.PROPOSAL, lambda r: prompts.proposal_prompt(q), PROPOSAL_SCHEMA, 0)
        if not proposals:
            return result("", False, 0, {}, error="no participant answered")
        try:
            draft = (await self._ask(mod, prompts.DRAFT, prompts.draft_prompt(q, proposals), DRAFT_SCHEMA, 0, st))["draft"]
        except _Failed as e:
            return result("", False, 0, {}, error=f"the moderator failed: {e}")

        open_obj: dict[str, list[str]] = {}
        consensus, rounds = False, 0
        for n in range(1, self.max_rounds + 1):
            rounds = n
            await self._emit("round", n)
            reviews = await gather(prompts.REVIEW, lambda r: prompts.review_prompt(q, draft, {k: v for k, v in open_obj.items() if k != r}, n),
                                   REVIEW_SCHEMA, n)
            open_obj = {r: (v["objections"] or [v["proposed_change"]]) for r, v in reviews.items() if not v["agree"]}
            if len(active) < QUORUM:
                st.warnings.append(f"quorum lost: fewer than {QUORUM} participants still answer")
                break
            if all(r in reviews and reviews[r]["agree"] for r in active):
                consensus = True
                break
            if n == self.max_rounds:
                break
            try:
                rev = await self._ask(mod, prompts.REVISE, prompts.revise_prompt(q, draft, reviews, n), REVISE_SCHEMA, n, st)
            except _Failed as e:
                return result(draft, False, rounds, open_obj, error=f"the moderator failed: {e}")
            draft = rev["draft"]
            for x in rev["rulings"]:
                if isinstance(x.get("objection"), str) and x.get("decision") in ("accepted", "rejected") and x not in st.rulings:
                    st.rulings.append(x)

        dissent = {} if consensus else open_obj
        try:
            final = await self._ask(mod, prompts.FINAL, prompts.final_prompt(q, draft, st.rulings, dissent), FINAL_SCHEMA, rounds, st)
        except _Failed:
            st.warnings.append("the final summary failed; the agreed draft is shown instead")
            return result(draft, consensus, rounds, dissent)
        return result(draft, consensus, rounds, dissent, decision=final["decision"], reasons=final["reasons"])


class _State:
    def __init__(self):
        self.usage = Usage()
        self.warnings: list[str] = []
        self.transcript: list[Entry] = []
        self.rulings: list[dict] = []
