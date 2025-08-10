import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# Загружаем .env файл из корневой директории проекта
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Основные настройки бота
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_bot_token_here")
BOT_USERNAME = os.getenv("BOT_USERNAME", "your_bot_username")

# Telegram группа для публикации лотов
TELEGRAM_GROUP_ID = os.getenv("TELEGRAM_GROUP_ID", "-1002671995892")
TELEGRAM_CHANNEL_USERNAME = os.getenv("TELEGRAM_CHANNEL_USERNAME", "auction_channel")

# База данных
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///db.db")

# Логирование
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "bot.log")

# Аукцион
MIN_BID_INCREMENT = float(os.getenv("MIN_BID_INCREMENT", "1.0"))
AUCTION_DURATION_HOURS = int(os.getenv("AUCTION_DURATION_HOURS", "168"))  # 7 дней
COMMISSION_PERCENT = float(os.getenv("COMMISSION_PERCENT", "5.0"))  # 5%
PENALTY_PERCENT = float(os.getenv("PENALTY_PERCENT", "5.0"))  # 5% штраф

# Роли пользователей
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
SUPPORT_IDS = [
    int(x.strip()) for x in os.getenv("SUPPORT_IDS", "").split(",") if x.strip()
]
SUPER_ADMIN_IDS = [
    int(x.strip()) for x in os.getenv("SUPER_ADMIN_IDS", "").split(",") if x.strip()
]

# Автоставки
AUTO_BID_MIN_BALANCE = float(
    os.getenv("AUTO_BID_MIN_BALANCE", "100.0")
)  # Увеличено с 0.0
AUTO_BID_MIN_PAYMENTS = int(os.getenv("AUTO_BID_MIN_PAYMENTS", "1"))  # Увеличено с 0

# Уведомления
NOTIFICATION_INTERVAL_MINUTES = int(
    os.getenv("NOTIFICATION_INTERVAL_MINUTES", "2")
)  # Увеличено с 1

# Модерация
MAX_STRIKES = int(os.getenv("MAX_STRIKES", "3"))
LOT_APPROVAL_REQUIRED = os.getenv("LOT_APPROVAL_REQUIRED", "true").lower() == "true"

# Файлы и медиа
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "50"))  # MB
ALLOWED_FILE_TYPES = os.getenv("ALLOWED_FILE_TYPES", "jpg,jpeg,png,pdf,doc,docx").split(
    ","
)

# Система управления
MANAGEMENT_SYSTEM = os.getenv("MANAGEMENT_SYSTEM", "qt")  # django или qt

# Прогрессивная система ставок
BID_INCREMENT_RULES = {
    0: 1,  # 0-99₽ → шаг 1₽
    100: 5,  # 100-499₽ → шаг 5₽
    500: 10,  # 500-999₽ → шаг 10₽
    1000: 25,  # 1000-4999₽ → шаг 25₽
    5000: 50,  # 5000-9999₽ → шаг 50₽
    10000: 100,  # 10000+₽ → шаг 100₽
}

# Шаблоны документов
DOCUMENT_TEMPLATES = {
    "jewelry": {"title": "Акт передачи ювелирного изделия", "template": "jewelry.md"},
    "historical": {
        "title": "Акт передачи исторической ценности",
        "template": "historical.md",
    },
    "standard": {"title": "Акт передачи товара", "template": "standard.md"},
}

# Настройки безопасности
SECRET_KEY = os.getenv("SECRET_KEY", os.urandom(32).hex())  # Генерируем случайный ключ
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Настройки Telegram
TELEGRAM_API_TIMEOUT = int(os.getenv("TELEGRAM_API_TIMEOUT", "30"))
TELEGRAM_RETRY_DELAY = int(os.getenv("TELEGRAM_RETRY_DELAY", "5"))

# Настройки базы данных
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))
DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))

# Настройки аукциона
AUCTION_CHECK_INTERVAL = int(os.getenv("AUCTION_CHECK_INTERVAL", "60"))  # секунды
LOT_EXPIRY_NOTIFICATION_HOURS = int(os.getenv("LOT_EXPIRY_NOTIFICATION_HOURS", "24"))

# Настройки уведомлений
ENABLE_EMAIL_NOTIFICATIONS = (
    os.getenv("ENABLE_EMAIL_NOTIFICATIONS", "false").lower() == "true"
)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

# Настройки платежей
PAYMENT_GATEWAY = os.getenv("PAYMENT_GATEWAY", "test")  # test, yookassa, stripe
PAYMENT_CURRENCY = os.getenv("PAYMENT_CURRENCY", "RUB")

# Настройки модерации
MODERATION_AUTO_APPROVE = (
    os.getenv("MODERATION_AUTO_APPROVE", "false").lower() == "true"
)
MODERATION_REQUIRED_FIELDS = [
    "title",
    "description",
    "starting_price",
    "start_time",
    "end_time",
]

# Настройки отчетности
REPORTS_ENABLED = os.getenv("REPORTS_ENABLED", "true").lower() == "true"
REPORTS_RETENTION_DAYS = int(os.getenv("REPORTS_RETENTION_DAYS", "365"))

# Настройки кэширования
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))  # секунды

# Настройки мониторинга
MONITORING_ENABLED = os.getenv("MONITORING_ENABLED", "true").lower() == "true"
HEALTH_CHECK_INTERVAL = int(os.getenv("HEALTH_CHECK_INTERVAL", "300"))  # секунды

# Новые настройки для оптимизации
ENABLE_RATE_LIMITING = os.getenv("ENABLE_RATE_LIMITING", "true").lower() == "true"
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))  # запросов в минуту
ENABLE_COMPRESSION = os.getenv("ENABLE_COMPRESSION", "true").lower() == "true"
ENABLE_LOGGING_ROTATION = os.getenv("ENABLE_LOGGING_ROTATION", "true").lower() == "true"
LOG_MAX_SIZE = int(os.getenv("LOG_MAX_SIZE", "10"))  # MB
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))


def get_database_url() -> str:
    """Возвращает URL базы данных с параметрами пула"""
    if DATABASE_URL.startswith("sqlite"):
        return DATABASE_URL
    else:
        # Для PostgreSQL/MySQL добавляем параметры пула
        separator = "&" if "?" in DATABASE_URL else "?"
        return f"{DATABASE_URL}{separator}pool_size={DB_POOL_SIZE}&max_overflow={DB_MAX_OVERFLOW}&pool_timeout={DB_POOL_TIMEOUT}"


def validate_settings() -> List[str]:
    """Проверяет корректность настроек и возвращает список ошибок"""
    errors = []

    if BOT_TOKEN == "your_bot_token_here":
        errors.append("BOT_TOKEN не настроен")

    # Проверяем только формат ID канала, а не конкретное значение
    if not TELEGRAM_GROUP_ID.startswith("-100"):
        errors.append("TELEGRAM_GROUP_ID должен начинаться с -100")

    if COMMISSION_PERCENT < 0 or COMMISSION_PERCENT > 100:
        errors.append("COMMISSION_PERCENT должен быть от 0 до 100")

    if PENALTY_PERCENT < 0 or PENALTY_PERCENT > 100:
        errors.append("PENALTY_PERCENT должен быть от 0 до 100")

    if AUTO_BID_MIN_BALANCE < 0:
        errors.append("AUTO_BID_MIN_BALANCE не может быть отрицательным")

    if AUTO_BID_MIN_PAYMENTS < 0:
        errors.append("AUTO_BID_MIN_PAYMENTS не может быть отрицательным")

    if MIN_BID_INCREMENT <= 0:
        errors.append("MIN_BID_INCREMENT должен быть больше 0")

    return errors


def get_project_root() -> Path:
    """Возвращает корневую директорию проекта"""
    return Path(__file__).parent.parent


def get_media_path() -> Path:
    """Возвращает путь к медиа файлам"""
    return get_project_root() / "media"


def get_logs_path() -> Path:
    """Возвращает путь к логам"""
    return get_project_root() / "logs"
