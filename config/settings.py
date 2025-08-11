"""
Глобальные настройки приложения.

Все значения можно переопределить через переменные окружения.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List


# ---------- Загрузка .env (без внешних зависимостей) ----------
def _load_env_file() -> None:
    env_path = (
        get_project_root() / ".env"
        if "get_project_root" in globals()
        else Path(__file__).resolve().parents[1] / ".env"
    )
    try:
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                # Не перезаписываем уже заданные в окружении значения
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        # Тихо игнорируем проблемы с .env, продолжим с os.environ
        pass


# ---------- Пути ----------
def get_project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def get_logs_path() -> Path:
    return get_project_root() / "logs"


def get_media_path() -> Path:
    return get_project_root() / "media"


# ---------- Логирование ----------
# Загружаем переменные из .env до чтения значений
_load_env_file()

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: str = os.getenv("LOG_FILE", "system.log")


# ---------- Telegram ----------
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
BOT_USERNAME: str = os.getenv("BOT_USERNAME", "YourBotName")


# Канал/группа, куда публикуются лоты (ID группы начинается с -100...)
def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


TELEGRAM_GROUP_ID: int = _env_int("TELEGRAM_GROUP_ID", 0)
TELEGRAM_CHANNEL_USERNAME: str = os.getenv("TELEGRAM_CHANNEL_USERNAME", "your_channel")
TELEGRAM_API_TIMEOUT: int = _env_int("TELEGRAM_API_TIMEOUT", 30)
TELEGRAM_RETRY_DELAY: int = _env_int("TELEGRAM_RETRY_DELAY", 2)


# ---------- Уведомления ----------
NOTIFICATION_INTERVAL_MINUTES: int = _env_int("NOTIFICATION_INTERVAL_MINUTES", 5)


# ---------- Доступы/роли ----------
def _parse_ids(env_name: str) -> List[int]:
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return []
    ids: List[int] = []
    for token in raw.replace(";", ",").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            ids.append(int(token))
        except Exception:
            pass
    return ids


ADMIN_IDS: List[int] = _parse_ids("ADMIN_IDS")
SUPER_ADMIN_IDS: List[int] = _parse_ids("SUPER_ADMIN_IDS")
SUPPORT_IDS: List[int] = _parse_ids("SUPPORT_IDS")


# ---------- База данных ----------
DB_POOL_SIZE: int = _env_int("DB_POOL_SIZE", 5)
DB_MAX_OVERFLOW: int = _env_int("DB_MAX_OVERFLOW", 10)
DB_POOL_TIMEOUT: int = _env_int("DB_POOL_TIMEOUT", 30)


def get_database_url() -> str:
    # Формат: sqlite:///absolute_path/auction.db или любой валидный URL SQLAlchemy
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    db_path = get_project_root() / "auction.db"
    return f"sqlite:///{db_path.as_posix()}"


# ---------- Медиа/файлы ----------
MAX_FILE_SIZE: int = _env_int("MAX_FILE_SIZE", 10 * 1024 * 1024)  # 10 MB


# ---------- Бизнес-настройки/финансы ----------
def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


COMMISSION_PERCENT: float = _env_float("COMMISSION_PERCENT", 5.0)
PENALTY_PERCENT: float = _env_float("PENALTY_PERCENT", 5.0)

# Порог для автоставок (оставляем 0, чтобы автоставки были доступны всем)
AUTO_BID_MIN_BALANCE: float = _env_float("AUTO_BID_MIN_BALANCE", 500)
AUTO_BID_MIN_PAYMENTS: int = _env_int("AUTO_BID_MIN_PAYMENTS", 5)


# ---------- Отладка ----------
def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, None)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


DEBUG: bool = _env_bool("DEBUG", False)


# ---------- Валидация настроек (для run.py) ----------
def validate_settings() -> list[str]:
    errors: list[str] = []
    if not BOT_TOKEN:
        errors.append("BOT_TOKEN не задан (установите переменную окружения BOT_TOKEN)")
    if TELEGRAM_GROUP_ID == 0:
        errors.append(
            "TELEGRAM_GROUP_ID не задан или равен 0 (установите корректный ID канала/группы)"
        )
    # Дополнительно: можно проверять доступность путей/директорий
    return errors
