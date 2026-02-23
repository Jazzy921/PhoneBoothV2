from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    discord_bot_token: str
    command_prefix: str = "c."
    discord_application_id: str | None = None
    discord_guild_id: str | None = None


@lru_cache
def get_settings() -> BotSettings:
    return BotSettings()
