"""Telegram bot: one chat, the debate runs inside it.

The handlers are plain functions over the few message methods they use, so
they can be tested without Telegram. Only allowlisted users are served.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from html import escape

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from .app import make_engine, make_llm
from .config import Config
from .engine import QuestionError, validate_question
from .render import summary_html
from .roles import load_roles
from .store import Store

log = logging.getLogger("orchestrator.bot")

PRIVATE = "This is a private bot."
STILL_WORKING = "Still working on your previous question. I'll answer it first."
FAILED = "Something went wrong during the debate. Please try again."


@dataclass
class BotDeps:
    engine_factory: Callable  # on_event -> object with async run(question) -> Result
    store: Store
    allowed: frozenset[int]
    role_names: list[str] = field(default_factory=lambda: ["architect", "critic", "pragmatist"])
    running: set[int] = field(default_factory=set)


def _allowed(user_id: int, deps: BotDeps) -> bool:
    if user_id in deps.allowed:
        return True
    log.info("refused a message from user %s (not in ALLOWED_USER_IDS)", user_id)
    return False


async def handle_start(message, deps: BotDeps) -> None:
    if not _allowed(message.from_user.id, deps):
        await message.answer(PRIVATE)
        return
    names = ", ".join(deps.role_names)
    await message.answer(
        "Send me a question or a decision you are weighing.\n\n"
        f"The agents ({names}) each answer it, then argue in rounds until they all accept one answer. "
        "You get the decision, the reasons, and any objection that was still open at the end. "
        "The full debate is one tap away."
    )


def _status_text(event: tuple) -> str:
    return "Debating: first proposals…" if event[1] == 0 else f"Debating: round {event[1]}…"


async def handle_question(message, deps: BotDeps) -> None:
    uid = message.from_user.id
    if not _allowed(uid, deps):
        await message.answer(PRIVATE)
        return
    try:
        question = validate_question(message.text or "")
    except QuestionError as e:
        await message.answer(str(e))
        return
    if uid in deps.running:
        await message.answer(STILL_WORKING)
        return
    deps.running.add(uid)
    try:
        status = await message.answer("Debating: first proposals…")

        async def on_event(event: tuple) -> None:
            if event[0] == "round":
                try:
                    await status.edit_text(_status_text(event))
                except TelegramBadRequest:
                    pass  # "message is not modified" and similar

        result = await deps.engine_factory(on_event).run(question)
        debate_id = await asyncio.to_thread(deps.store.save, uid, result)
        await status.edit_text(f"Done in {result.rounds} round{'s' if result.rounds != 1 else ''}.")
        parts = summary_html(result)
        button = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Show debate", callback_data=f"debate:{debate_id}")]])
        for i, part in enumerate(parts):
            await message.answer(part, parse_mode="HTML", reply_markup=button if i == len(parts) - 1 else None)
    except Exception:
        log.exception("debate failed for user %s", uid)
        await message.answer(FAILED)
    finally:
        deps.running.discard(uid)


async def handle_show_debate(callback, deps: BotDeps) -> None:
    uid = callback.from_user.id
    try:
        debate_id = int((callback.data or "").split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Unknown debate.", show_alert=True)
        return
    found = await asyncio.to_thread(deps.store.get, debate_id, uid)
    if not found:
        await callback.answer("This debate is not available.", show_alert=True)
        return
    question, markdown = found
    short = question if len(question) <= 200 else question[:199] + "…"
    await callback.message.answer_document(
        BufferedInputFile(markdown.encode("utf-8"), filename=f"debate-{debate_id}.md"),
        caption=escape(short, quote=False),
    )
    await callback.answer()


def build_dispatcher(deps: BotDeps) -> Dispatcher:
    dp = Dispatcher()

    @dp.message(CommandStart())
    @dp.message(Command("help"))
    async def _start(message):
        await handle_start(message, deps)

    @dp.message(F.text)
    async def _question(message):
        await handle_question(message, deps)

    @dp.callback_query(F.data.startswith("debate:"))
    async def _debate(callback):
        await handle_show_debate(callback, deps)

    return dp


async def run_bot(cfg: Config) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    llm = make_llm(cfg)
    roles = load_roles(cfg.roles_path)
    deps = BotDeps(
        engine_factory=lambda on_event: make_engine(cfg, llm, on_event),
        store=Store(cfg.db_path),
        allowed=cfg.allowed_user_ids,
        role_names=[r.id for r in roles.participants],
    )
    bot = Bot(cfg.bot_token)
    log.info("bot started in %s mode for %d allowed user(s)", cfg.mode, len(cfg.allowed_user_ids))
    try:
        await build_dispatcher(deps).start_polling(bot)
    finally:
        await bot.session.close()
        if hasattr(llm, "aclose"):
            await llm.aclose()
