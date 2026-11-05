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

    # Verification agent (off by default; needs an OpenAI-compatible API key)
    enable_agent: bool = False
    openrouter_api_key: Optional[str] = None
    agent_api_key: Optional[str] = None  # any OpenAI-compatible provider (Groq, Cerebras...); falls back to OPENROUTER_API_KEY
    agent_base_url: str = "https://openrouter.ai/api/v1"
    agent_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    agent_max_per_run: int = 10
    agent_trace_file: str = "data/agent_traces.jsonl"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

settings = Settings()
