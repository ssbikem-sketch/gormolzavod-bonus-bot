"""Қолданба баптауларын орта айнымалыларынан немесе .env файлынан оқу."""
from dataclasses import dataclass
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    admin_ids: frozenset[int]
    database_path: Path
    log_level: int

def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or token.startswith("1234567890:"):
        raise RuntimeError(".env файлына жарамды BOT_TOKEN мәнін енгізіңіз")
    try:
        admin_ids = frozenset(
            int(item.strip())
            for item in os.getenv("ADMIN_IDS", "").split(",")
            if item.strip()
        )
    except ValueError as error:
        raise ValueError("ADMIN_IDS ішінде үтірмен бөлінген Telegram ID мәндері болуы керек") from error
    if any(admin_id <= 0 for admin_id in admin_ids):
        raise ValueError("Әкімші Telegram ID мәндері оң сан болуы керек")

    database_path = Path(os.getenv("DATABASE_PATH", "data/bonus_bot.sqlite3").strip())
    if not database_path.is_absolute():
        database_path = BASE_DIR / database_path
    level_name = os.getenv("LOG_LEVEL", "INFO").upper().strip()
    log_level = getattr(logging, level_name, None)
    if not isinstance(log_level, int):
        raise ValueError("LOG_LEVEL мәні жарамсыз")
    return Settings(token, admin_ids, database_path, log_level)
