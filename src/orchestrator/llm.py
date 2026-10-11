"""Model clients: OpenRouter for real models, and a scripted demo client."""

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

import httpx

from . import prompts

OPENROUTER_URL = "https://openrouter.ai/api/v1"


@dataclass(frozen=True)
class Completion:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    usd: float = 0.0


class LLMError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"model API error {status}: {message}" if status else message)
        self.status = status


class LLM(Protocol):
    async def complete(self, model: str, system: str, user: str) -> Completion: ...


class OpenRouterClient:
    def __init__(self, api_key: str, base_url: str = OPENROUTER_URL, timeout: float = 60.0, http: httpx.AsyncClient | None = None):
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._http = http or httpx.AsyncClient(timeout=timeout)

    async def complete(self, model: str, system: str, user: str) -> Completion:
        try:
            res = await self._http.post(
                f"{self._base}/chat/completions",
                headers={"Authorization": f"Bearer {self._key}"},
                json={
                    "model": model,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "usage": {"include": True},
                },
            )
        except httpx.TimeoutException:
            raise LLMError(0, f"{model}: the model did not answer in time") from None
        except httpx.HTTPError as e:
            raise LLMError(0, f"{model}: {e}") from None
        data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
        if res.status_code != 200:
            msg = (data.get("error") or {}).get("message") or res.reason_phrase
            raise LLMError(res.status_code, f"{model}: {msg}")
        choices = data.get("choices") or []
        if not choices or not (choices[0].get("message") or {}).get("content"):
            raise LLMError(0, f"{model}: empty answer")
        usage = data.get("usage") or {}
        return Completion(
            text=choices[0]["message"]["content"],
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
            usd=float(usage.get("cost") or 0.0),
        )

    async def aclose(self) -> None:
        await self._http.aclose()


def scenario(question: str) -> int:
    """Which demo script a question plays: 0 quick consensus, 1 objection accepted, 2 lasting dissent."""
    return hashlib.sha256(question.strip().encode()).digest()[0] % 3


def _short(q: str, n: int = 90) -> str:
    q = " ".join(q.split())
    return q if len(q) <= n else q[: n - 1] + "…"


class DemoClient:
    """Plays scripted parts so the whole debate runs without keys.

    The script depends only on the question, so the same question always
    plays out the same way. Texts are templates that quote the question.
    """

    async def complete(self, model: str, system: str, user: str) -> Completion:
        role = prompts.marker(system, "role") or "?"
        phase = prompts.marker(user, "phase")
        rnd = int(prompts.marker(user, "round") or 0)
        q = prompts.question_of(user)
        out = self._play(role, phase, rnd, _short(q), scenario(q))
        text = json.dumps(out, ensure_ascii=False)
        return Completion(text=text, tokens_in=len(system + user) // 4, tokens_out=len(text) // 4, usd=0.0)

    def _play(self, role: str, phase: str | None, rnd: int, q: str, s: int) -> dict:
        if phase == prompts.PROPOSAL:
            return {
                "architect": {"position": f"For \"{q}\": build the smallest version that works end to end, behind a flag.",
                              "reasons": ["a working slice shows the real problems early", "a flag makes it easy to turn off"]},
                "critic": {"position": f"For \"{q}\": do it only with a way to measure the result and a way back.",
                           "reasons": ["without a metric nobody knows if it helped", "a rollback limits the damage"]},
                "pragmatist": {"position": f"For \"{q}\": take the cheapest option that solves today's problem.",
                               "reasons": ["time is the scarcest resource", "simple things are easier to maintain"]},
            }.get(role, {"position": f"For \"{q}\": no strong view.", "reasons": []})
        if phase == prompts.DRAFT:
            return {"draft": f"Ship the smallest working version of \"{q}\" behind a flag, keep it cheap, and decide later whether to extend it."}
        if phase == prompts.REVIEW:
            if s == 1 and role == "critic" and rnd == 1:
                return {"agree": False, "objections": ["The draft does not say how we will know it worked."],
                        "proposed_change": "Name one metric and check it two weeks after release."}
            if s == 2 and role == "pragmatist":
                return {"agree": False, "objections": ["A flag and a metric are more than the first step needs."],
                        "proposed_change": "Ship it plainly and add the flag only if something breaks."}
            if s == 2 and role == "critic" and rnd == 1:
                return {"agree": False, "objections": ["There is no rollback plan."],
                        "proposed_change": "Keep the flag so it can be switched off in a minute."}
            return {"agree": True, "objections": [], "proposed_change": ""}
        if phase == prompts.REVISE:
            if s == 1:
                return {"draft": f"Ship the smallest working version of \"{q}\" behind a flag, keep it cheap, and check one agreed metric two weeks after release.",
                        "rulings": [{"objection": "The draft does not say how we will know it worked.", "decision": "accepted",
                                     "reason": "Without a metric the follow-up decision is a guess."}]}
            return {"draft": f"Ship the smallest working version of \"{q}\" behind a flag so it can be switched off in a minute; keep it cheap.",
                    "rulings": [{"objection": "There is no rollback plan.", "decision": "accepted", "reason": "The flag is the rollback; now it is stated."},
                                {"objection": "A flag and a metric are more than the first step needs.", "decision": "rejected",
                                 "reason": "A flag costs little and is the only fast way back."}]}
        if phase == prompts.FINAL:
            reasons = ["A small working version shows real problems early.", "A flag keeps the way back short."]
            if s == 1:
                reasons.append("One metric, checked after two weeks, decides whether to extend it.")
            return {"decision": f"Do \"{q}\" as a small version behind a flag, and keep it cheap.", "reasons": reasons}
        return {}
