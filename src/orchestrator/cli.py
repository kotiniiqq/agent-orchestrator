"""Command line: ask a question, or run the Telegram bot."""

import argparse
import asyncio
import os
import sys
from collections.abc import Mapping
from dataclasses import replace

from .app import make_engine, make_llm
from .config import Config, ConfigError
from .engine import QuestionError, validate_question
from .render import debate_markdown
from .roles import RolesError
from .transcript import Result


def _plain(r: Result) -> str:
    lines = ["Decision", "  " + (r.decision or "(no decision)")]
    if r.reasons:
        lines += ["", "Why"] + [f"  - {x}" for x in r.reasons]
    if r.dissent:
        lines += ["", "Dissent"] + [f"  - {role}: {o}" for role, objs in r.dissent.items() for o in objs]
    rounds = f"{r.rounds} round{'s' if r.rounds != 1 else ''}"
    status = f"Consensus after {rounds}" if r.consensus else f"No consensus after {rounds}"
    tokens = r.usage.tokens_in + r.usage.tokens_out
    if tokens:
        status += f", ${r.usage.usd:.4f}, {tokens:,} tokens"
    lines += ["", status]
    if r.error:
        lines.append(f"Stopped early: {r.error}")
    lines += [f"warning: {w}" for w in r.warnings]
    return "\n".join(lines)


def _progress(event: tuple) -> None:
    if event[0] == "round":
        print("proposals" if event[1] == 0 else f"round {event[1]}", file=sys.stderr, flush=True)
    elif event[0] == "done":
        print(f"  {event[1]}: {event[2]} done", file=sys.stderr, flush=True)


async def _ask(cfg: Config, question: str, transcript: str | None) -> int:
    llm = make_llm(cfg)
    try:
        r = await make_engine(cfg, llm, on_event=_progress).run(question)
    finally:
        if hasattr(llm, "aclose"):
            await llm.aclose()
    print(_plain(r))
    if transcript:
        with open(transcript, "w", encoding="utf-8") as f:
            f.write(debate_markdown(r))
        print(f"debate written to {transcript}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="orchestrator", description="Role-based agents argue until they agree.")
    sub = p.add_subparsers(dest="cmd", required=True)
    ask = sub.add_parser("ask", help="ask one question and print the result")
    ask.add_argument("question")
    ask.add_argument("--live", action="store_true", help="use real models via OpenRouter (needs OPENROUTER_API_KEY)")
    ask.add_argument("--rounds", type=int, help="maximum review rounds")
    ask.add_argument("--transcript", help="write the full debate as Markdown to this file")
    sub.add_parser("bot", help="run the Telegram bot")
    args = p.parse_args(argv)
    env = dict(os.environ if env is None else env)
    if getattr(args, "live", False):
        env["MODE"] = "live"
    try:
        cfg = Config.from_env(env)
        if args.cmd == "bot":
            from .bot import run_bot

            cfg.require_bot()
            asyncio.run(run_bot(cfg))
            return 0
        if args.rounds:
            if args.rounds < 1:
                raise ConfigError("--rounds must be at least 1")
            cfg = replace(cfg, max_rounds=args.rounds)
        question = validate_question(args.question)
        return asyncio.run(_ask(cfg, question, args.transcript))
    except (ConfigError, QuestionError, RolesError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
