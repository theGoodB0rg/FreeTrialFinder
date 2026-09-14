import os
from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    discord_webhook_url: Optional[str] = None
    min_score: int = 40
    state_file: str = "data/seen_deals.json"
    enable_telegram: bool = True
    enable_discord: bool = True
    enable_console: bool = True

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

settings = Settings()
