"""Turn a Result into a Telegram summary (HTML) and a full debate (Markdown)."""

from html import escape

from . import prompts
from .transcript import Result

LIMIT = 4096  # Telegram message length


def _status(r: Result) -> str:
    head = f"Consensus after {r.rounds} round{'s' if r.rounds != 1 else ''}" if r.consensus else f"No consensus after {r.rounds} round{'s' if r.rounds != 1 else ''}"
    tokens = r.usage.tokens_in + r.usage.tokens_out
    return f"{head} · ${r.usage.usd:.4f} · {tokens:,} tokens" if tokens else head


def _split_escaped(piece: str, limit: int) -> list[str]:
    """Cut an escaped string into pieces of at most limit, never inside an entity."""
    out = []
    while len(piece) > limit:
        cut = limit
        amp = piece.rfind("&", 0, cut)
        if amp != -1 and ";" not in piece[amp:cut]:
            cut = amp  # the entity starting at amp would be cut in half
        out.append(piece[:cut])
        piece = piece[cut:]
    return out + [piece]


def _chunks(text: str, limit: int) -> list[str]:
    """Escape text and cut it at spaces so that no piece exceeds limit."""
    out, cur = [], ""
    for word in text.split(" "):
        piece = escape(word if not cur else " " + word, quote=False)
        if cur and len(cur) + len(piece) > limit:
            out.append(cur)
            cur, piece = "", escape(word, quote=False)
        if len(piece) > limit:
            *full, piece = _split_escaped(piece, limit)
            out += full
        cur += piece
    if cur:
        out.append(cur)
    return out


def summary_html(r: Result) -> list[str]:
    blocks = ["<b>Decision</b>"] + _chunks(r.decision or "(no decision)", LIMIT - 100)
    if r.reasons:
        blocks.append("<b>Why</b>\n" + "\n".join("• " + escape(x, quote=False) for x in r.reasons[:5]))
    if r.dissent:
        lines = [f"• <i>{escape(role, quote=False)}</i>: {escape(o, quote=False)}" for role, objs in r.dissent.items() for o in objs]
        blocks.append("<b>Dissent</b>\n" + "\n".join(lines))
    tail = f"<i>{escape(_status(r), quote=False)}</i>"
    if r.error:
        tail += f"\n⚠ Stopped early: {escape(r.error, quote=False)}"
    if r.warnings:
        tail += f"\n⚠ {len(r.warnings)} warning{'s' if len(r.warnings) != 1 else ''}, see the debate"
    blocks.append(tail)

    messages, cur = [], ""
    for b in blocks:
        for piece in ([b] if len(b) <= LIMIT else _chunks(b, LIMIT)):
            sep = "\n\n" if cur else ""
            if len(cur) + len(sep) + len(piece) > LIMIT:
                messages.append(cur)
                cur, sep = "", ""
            cur += sep + piece
    if cur:
        messages.append(cur)
    return messages


def _bullets(items) -> str:
    return "\n".join(f"- {x}" for x in items) if items else "- (none)"


def debate_markdown(r: Result) -> str:
    out = ["# Debate", "", f"**Question:** {r.question}", ""]
    last_round = -1
    for e in r.transcript:
        if e.phase == prompts.FINAL:
            continue
        if e.round != last_round:
            out += ["## Proposals" if e.round == 0 else f"## Round {e.round}", ""]
            last_round = e.round
        p = e.payload
        if p is None:
            out += [f"### {e.role} ({e.phase})", "", f"_{e.warning}_", ""]
        elif e.phase == prompts.PROPOSAL:
            out += [f"### {e.role}", "", p["position"], "", _bullets(p["reasons"]), ""]
        elif e.phase == prompts.DRAFT:
            out += ["### moderator: first draft", "", p["draft"], ""]
        elif e.phase == prompts.REVIEW:
            if p["agree"]:
                out += [f"### {e.role}: agrees", ""]
            else:
                out += [f"### {e.role}: objects", "", _bullets(p["objections"]), "", f"Wants: {p['proposed_change']}", ""]
        elif e.phase == prompts.REVISE:
            out += ["### moderator: rulings", ""]
            out += [f"- **{x.get('decision')}**: {x.get('objection')} ({x.get('reason', '')})" for x in p["rulings"]] or ["- (none)"]
            out += ["", "Revised draft:", "", p["draft"], ""]
    out += ["## Result", "", r.decision or "(no decision)", "", "**Why**", "", _bullets(r.reasons), ""]
    if r.dissent:
        out += ["**Dissent**", ""] + [f"- {role}: {o}" for role, objs in r.dissent.items() for o in objs] + [""]
    if r.error:
        out += [f"**Stopped early:** {r.error}", ""]
    if r.warnings:
        out += ["**Warnings**", "", _bullets(r.warnings), ""]
    out += [f"_{_status(r)}_", "", "| role | calls | tokens in | tokens out | USD |", "|---|---|---|---|---|"]
    out += [f"| {role} | {u['calls']} | {u['tokens_in']} | {u['tokens_out']} | {u['usd']:.4f} |" for role, u in r.usage.by_role.items()]
    return "\n".join(out) + "\n"
