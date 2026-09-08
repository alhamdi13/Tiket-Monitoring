"""
config.py - Konfigurasi Terpusat untuk Flight Monitor Pro.
Mendukung pembacaan dari file .env dengan fallback dinamis ke database SQLite.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv
import database

load_dotenv()


@dataclass
class Config:
    # Server Web
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))

    # Logging
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    @property
    def telegram_bot_token(self) -> str:
        # Prioritaskan database setting jika ada, fallback ke .env
        val = database.get_setting("telegram_bot_token")
        if val:
            return val
        return os.getenv("TELEGRAM_BOT_TOKEN", "")

    @property
    def telegram_chat_id(self) -> str:
        val = database.get_setting("telegram_chat_id")
        if val:
            return val
        return os.getenv("TELEGRAM_CHAT_ID", "")

    @property
    def auto_scan_enabled(self) -> bool:
        val = database.get_setting("auto_scan_enabled", "true")
        return val.lower() in ("true", "1", "yes")

    @property
    def mock_simulation_enabled(self) -> bool:
        val = database.get_setting("mock_simulation_enabled", "true")
        return val.lower() in ("true", "1", "yes")

    def update_telegram_credentials(self, token: str, chat_id: str):
        database.set_setting("telegram_bot_token", token.strip())
        database.set_setting("telegram_chat_id", chat_id.strip())


cfg = Config()
