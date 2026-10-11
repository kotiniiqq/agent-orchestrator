"""Settings from the environment."""

from collections.abc import Mapping
from dataclasses import dataclass


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    mode: str  # demo (scripted, no keys) or live (OpenRouter)
    openrouter_key: str
    bot_token: str
    allowed_user_ids: frozenset[int]
    max_rounds: int
    db_path: str
    roles_path: str

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Config":
        mode = env.get("MODE", "demo") or "demo"
        if mode not in ("demo", "live"):
            raise ConfigError(f"MODE must be demo or live, got {mode!r}")
        key = env.get("OPENROUTER_API_KEY", "")
        if mode == "live" and not key:
            raise ConfigError("OPENROUTER_API_KEY is required for MODE=live")
        try:
            rounds = int(env.get("MAX_ROUNDS", "4") or "4")
        except ValueError:
            raise ConfigError("MAX_ROUNDS must be a whole number") from None
        if rounds < 1:
            raise ConfigError("MAX_ROUNDS must be at least 1")
        try:
            allowed = frozenset(int(x) for x in env.get("ALLOWED_USER_IDS", "").split(",") if x.strip())
        except ValueError:
            raise ConfigError("ALLOWED_USER_IDS must be comma-separated Telegram user ids") from None
        return cls(
            mode=mode,
            openrouter_key=key,
            bot_token=env.get("TELEGRAM_BOT_TOKEN", ""),
            allowed_user_ids=allowed,
            max_rounds=rounds,
            db_path=env.get("DB_PATH", "orchestrator.db") or "orchestrator.db",
            roles_path=env.get("ROLES_PATH", "roles.yaml") or "roles.yaml",
        )

    def require_bot(self) -> None:
        if not self.bot_token:
            raise ConfigError("TELEGRAM_BOT_TOKEN is required to run the bot")
        if not self.allowed_user_ids:
            raise ConfigError("ALLOWED_USER_IDS is required to run the bot (it is a personal tool)")
