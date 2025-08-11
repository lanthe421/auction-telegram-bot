"""
Утилиты для работы со временем
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import pytz

logger = logging.getLogger(__name__)

# Московское время
MOSCOW_TZ = pytz.timezone("Europe/Moscow")

# Константы для автоматического продления
AUTO_EXTENSION_MINUTES = 10  # На сколько минут продлевать
LAST_MINUTE_THRESHOLD = 1  # За сколько минут до конца активировать продление


def get_moscow_time() -> datetime:
    """Возвращает текущее время в московском часовом поясе"""
    return datetime.now(MOSCOW_TZ)


def utc_to_moscow(utc_time: datetime) -> datetime:
    """Конвертирует UTC время в московское"""
    if utc_time.tzinfo is None:
        utc_time = utc_time.replace(tzinfo=pytz.UTC)
    return utc_time.astimezone(MOSCOW_TZ)


def moscow_to_utc(moscow_time: datetime) -> datetime:
    """Конвертирует московское время в UTC"""
    if moscow_time.tzinfo is None:
        moscow_time = moscow_time.replace(tzinfo=MOSCOW_TZ)
    return moscow_time.astimezone(pytz.UTC)


def format_moscow_time(dt: datetime, format_str: str = "%d.%m.%Y %H:%M") -> str:
    """Форматирует время в московском часовом поясе"""
    moscow_dt = utc_to_moscow(dt) if dt.tzinfo else dt.replace(tzinfo=MOSCOW_TZ)
    return moscow_dt.strftime(format_str)


def is_lot_ended(lot_end_time: datetime) -> bool:
    """Проверяет, закончился ли лот"""
    if not lot_end_time:
        return False

    # Ensure both times are timezone-aware
    now = get_moscow_time()
    if lot_end_time.tzinfo is None:
        lot_end_time = lot_end_time.replace(tzinfo=pytz.UTC)

    return lot_end_time <= now


def get_time_until_end(lot_end_time: datetime) -> Optional[timedelta]:
    """Возвращает время до окончания лота"""
    if not lot_end_time:
        return None

    # Ensure both times are timezone-aware
    now = get_moscow_time()
    if lot_end_time.tzinfo is None:
        lot_end_time = lot_end_time.replace(tzinfo=pytz.UTC)

    return lot_end_time - now


def should_extend_auction(lot_end_time: datetime) -> bool:
    """
    Проверяет, нужно ли продлить аукцион.
    Возвращает True, если до конца аукциона осталось меньше LAST_MINUTE_THRESHOLD минут.
    """
    if not lot_end_time:
        return False

    # Ensure both times are timezone-aware
    now = get_moscow_time()
    if lot_end_time.tzinfo is None:
        lot_end_time = lot_end_time.replace(tzinfo=pytz.UTC)

    time_left = lot_end_time - now

    # Проверяем, что аукцион еще не закончился и осталось меньше порогового времени
    return time_left.total_seconds() > 0 and time_left.total_seconds() <= (
        LAST_MINUTE_THRESHOLD * 60
    )


def extend_auction_end_time(lot_end_time: datetime) -> datetime:
    """
    Продлевает время окончания аукциона на AUTO_EXTENSION_MINUTES минут.
    """
    if not lot_end_time:
        return lot_end_time

    new_end_time = lot_end_time + timedelta(minutes=AUTO_EXTENSION_MINUTES)
    logger.info(
        f"Аукцион продлен на {AUTO_EXTENSION_MINUTES} минут. Новое время окончания: {new_end_time}"
    )
    return new_end_time


def get_extension_message(old_end_time: datetime, new_end_time: datetime) -> str:
    """
    Возвращает сообщение о продлении аукциона.
    """
    old_time_str = format_moscow_time(old_end_time, "%H:%M")
    new_time_str = format_moscow_time(new_end_time, "%H:%M")

    return f"""
⏰ <b>Аукцион продлен!</b>

🔄 Из-за ставки в последнюю минуту аукцион автоматически продлен на {AUTO_EXTENSION_MINUTES} минут.

📅 Новое время окончания: {new_time_str} (было {old_time_str})

🎯 Успейте сделать свою ставку!
    """.strip()
