"""Загрузка конфигурации из переменных окружения (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    openai_api_key: str
    openai_model: str
    max_file_size_bytes: int


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Переменная окружения {name} не задана. "
            f"Скопируйте .env.example в .env и заполните значения."
        )
    return value


def load_settings() -> Settings:
    return Settings(
        telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
        openai_api_key=_require("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        max_file_size_bytes=int(os.getenv("MAX_FILE_SIZE_BYTES", "2097152")),
    )
