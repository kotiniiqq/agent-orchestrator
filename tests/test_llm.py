import json

import httpx
import pytest
import respx

from orchestrator import prompts
from orchestrator.jsonout import STRS, parse
from orchestrator.llm import DemoClient, LLMError, OpenRouterClient, scenario

BASE = "https://openrouter.test/api/v1"


@respx.mock
async def test_openrouter_request_and_usage():
    route = respx.post(f"{BASE}/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"content": '{"a": 1}'}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30, "cost": 0.00042},
        })
    )
    c = OpenRouterClient("k-test", base_url=BASE)
    out = await c.complete("x/model", "sys", "user text")
    req = route.calls[0].request
    body = json.loads(req.content)
    assert req.headers["authorization"] == "Bearer k-test"
    assert body["model"] == "x/model" and body["usage"] == {"include": True}
    assert body["messages"] == [{"role": "system", "content": "sys"}, {"role": "user", "content": "user text"}]
    assert (out.text, out.tokens_in, out.tokens_out, out.usd) == ('{"a": 1}', 120, 30, 0.00042)


@respx.mock
@pytest.mark.parametrize("status, msg", [(401, "No auth credentials found"), (429, "Rate limit exceeded")])
async def test_openrouter_errors(status, msg):
    respx.post(f"{BASE}/chat/completions").mock(return_value=httpx.Response(status, json={"error": {"message": msg}}))
    with pytest.raises(LLMError) as e:
        await OpenRouterClient("k", base_url=BASE).complete("m", "s", "u")
    assert e.value.status == status and msg in str(e.value)


@respx.mock
async def test_openrouter_empty_choice_is_an_error():
    respx.post(f"{BASE}/chat/completions").mock(return_value=httpx.Response(200, json={"choices": []}))
    with pytest.raises(LLMError):
        await OpenRouterClient("k", base_url=BASE).complete("m", "s", "u")


def question_for(s: int) -> str:
    for i in range(100):
        q = f"Should we add caching to the reports service? v{i}"
        if scenario(q) == s:
            return q
    raise AssertionError("no question found")


async def review(client, role, q, round_no):
    out = await client.complete("m", prompts.system_prompt(role, "job", False), prompts.review_prompt(q, "draft", {}, round_no))
    return parse(out.text, {"agree": bool, "objections": STRS, "proposed_change": str})


async def test_demo_is_deterministic_and_valid():
    c = DemoClient()
    q = question_for(0)
    a = await c.complete("m", prompts.system_prompt("architect", "job", False), prompts.proposal_prompt(q))
    b = await c.complete("m", prompts.system_prompt("architect", "job", False), prompts.proposal_prompt(q))
    assert a.text == b.text and a.usd == 0
    assert q in parse(a.text, {"position": str, "reasons": STRS})["position"]


async def test_demo_scenarios():
    c = DemoClient()
    q0, q1, q2 = question_for(0), question_for(1), question_for(2)
    assert all([(await review(c, r, q0, 1))["agree"] for r in ("architect", "critic", "pragmatist")])
    assert not (await review(c, "critic", q1, 1))["agree"]
    assert (await review(c, "critic", q1, 2))["agree"]
    for n in (1, 2, 3, 4):
        assert not (await review(c, "pragmatist", q2, n))["agree"]
    assert (await review(c, "critic", q2, 2))["agree"]
