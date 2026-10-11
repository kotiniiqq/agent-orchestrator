"""Prompts for each phase of a debate.

Every prompt carries small machine-readable markers ([[role:..]], [[phase:..]],
[[round:..]], the question between [[question]] tags). Real models ignore
them; the demo client uses them to play its scripted part.
"""

import json
import re

PROPOSAL, DRAFT, REVIEW, REVISE, FINAL = "proposal", "draft", "review", "revise", "final"

_RULES = (
    "Reply with one JSON object only, no other text. Be concrete and brief: "
    "at most 120 words per text field. Write in the language of the question."
)


def system_prompt(role_id: str, job: str, moderator: bool) -> str:
    who = "the moderator of a debate between expert agents" if moderator else f"the {role_id} in a debate between expert agents"
    return f"[[role:{role_id}]]\nYou are {who}. Your job: {job}\n{_RULES}"


def _q(question: str) -> str:
    return f"[[question]]{question}[[/question]]"


def proposal_prompt(question: str) -> str:
    return (
        f"[[phase:{PROPOSAL}]]\nQuestion:\n{_q(question)}\n\n"
        'Give your own answer, independently of the others. JSON: {"position": "...", "reasons": ["..."]}'
    )


def draft_prompt(question: str, proposals: dict[str, dict]) -> str:
    return (
        f"[[phase:{DRAFT}]]\nQuestion:\n{_q(question)}\n\nProposals:\n{json.dumps(proposals, ensure_ascii=False, indent=1)}\n\n"
        "Merge them into one draft answer that keeps what is strongest in each. "
        'JSON: {"draft": "..."}'
    )


def review_prompt(question: str, draft: str, open_objections: dict[str, list[str]], round_no: int) -> str:
    return (
        f"[[phase:{REVIEW}]][[round:{round_no}]]\nQuestion:\n{_q(question)}\n\nCurrent draft:\n{draft}\n\n"
        f"Objections still open from others: {json.dumps(open_objections, ensure_ascii=False)}\n\n"
        "Do you accept this draft as the answer? Agree only if you would sign it. If not, list your objections and the change you want. "
        'JSON: {"agree": true|false, "objections": ["..."], "proposed_change": "..."}'
    )


def revise_prompt(question: str, draft: str, reviews: dict[str, dict], round_no: int) -> str:
    return (
        f"[[phase:{REVISE}]][[round:{round_no}]]\nQuestion:\n{_q(question)}\n\nCurrent draft:\n{draft}\n\n"
        f"Reviews:\n{json.dumps(reviews, ensure_ascii=False, indent=1)}\n\n"
        "Rule on every objection: accept it and change the draft, or reject it with a reason. Do not average opinions. "
        'JSON: {"draft": "...", "rulings": [{"objection": "...", "decision": "accepted"|"rejected", "reason": "..."}]}'
    )


def final_prompt(question: str, draft: str, rulings: list[dict], dissent: dict[str, list[str]]) -> str:
    return (
        f"[[phase:{FINAL}]]\nQuestion:\n{_q(question)}\n\nAgreed draft:\n{draft}\n\n"
        f"Rulings made during the debate: {json.dumps(rulings, ensure_ascii=False)}\n"
        f"Objections still open: {json.dumps(dissent, ensure_ascii=False)}\n\n"
        "Write the final answer for the person who asked: the decision and the key reasons (at most 5). "
        'JSON: {"decision": "...", "reasons": ["..."]}'
    )


def marker(text: str, name: str) -> str | None:
    m = re.search(rf"\[\[{name}:([^\]]+)\]\]", text)
    return m.group(1) if m else None


def question_of(text: str) -> str:
    m = re.search(r"\[\[question\]\](.*?)\[\[/question\]\]", text, re.S)
    return m.group(1) if m else ""
