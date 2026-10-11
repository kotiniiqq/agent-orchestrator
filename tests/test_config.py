import pytest

from orchestrator.config import Config, ConfigError


def test_defaults_are_demo():
    c = Config.from_env({})
    assert c.mode == "demo" and c.max_rounds == 4 and c.allowed_user_ids == frozenset()
    assert c.db_path == "orchestrator.db" and c.roles_path == "roles.yaml"


def test_live_needs_a_key():
    with pytest.raises(ConfigError, match="OPENROUTER_API_KEY"):
        Config.from_env({"MODE": "live"})


def test_allowed_ids_and_rounds_are_parsed():
    c = Config.from_env({"ALLOWED_USER_IDS": "12, 34", "MAX_ROUNDS": "2"})
    assert c.allowed_user_ids == frozenset({12, 34}) and c.max_rounds == 2


@pytest.mark.parametrize(
    "env, message",
    [
        ({"MODE": "magic"}, "MODE"),
        ({"MAX_ROUNDS": "0"}, "MAX_ROUNDS"),
        ({"MAX_ROUNDS": "x"}, "MAX_ROUNDS"),
        ({"ALLOWED_USER_IDS": "12,abc"}, "ALLOWED_USER_IDS"),
    ],
)
def test_bad_values(env, message):
    with pytest.raises(ConfigError, match=message):
        Config.from_env(env)


def test_bot_needs_token_and_allowlist():
    with pytest.raises(ConfigError, match="TELEGRAM_BOT_TOKEN"):
        Config.from_env({}).require_bot()
    with pytest.raises(ConfigError, match="ALLOWED_USER_IDS"):
        Config.from_env({"TELEGRAM_BOT_TOKEN": "t"}).require_bot()
    Config.from_env({"TELEGRAM_BOT_TOKEN": "t", "ALLOWED_USER_IDS": "1"}).require_bot()
