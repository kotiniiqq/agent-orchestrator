"""Wiring shared by the CLI and the bot."""

from collections.abc import Callable

from .config import Config
from .engine import Deliberation
from .llm import LLM, DemoClient, OpenRouterClient
from .roles import load_roles


def make_llm(cfg: Config) -> LLM:
    return OpenRouterClient(cfg.openrouter_key) if cfg.mode == "live" else DemoClient()


def make_engine(cfg: Config, llm: LLM, on_event: Callable | None = None) -> Deliberation:
    return Deliberation(llm, load_roles(cfg.roles_path), max_rounds=cfg.max_rounds, on_event=on_event)
