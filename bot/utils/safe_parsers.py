"""
Безопасные функции для парсинга callback_data
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def safe_extract_id(
    callback_data: str, separator: str = ":", index: int = 1
) -> Optional[int]:
    """
    Безопасно извлекает ID из callback_data

    Args:
        callback_data: Строка callback_data
        separator: Разделитель (по умолчанию ":")
        index: Индекс элемента после разделения (по умолчанию 1)

    Returns:
        ID как int или None в случае ошибки
    """
    try:
        if not callback_data:
            return None

        parts = callback_data.split(separator)
        if len(parts) <= index:
            logger.warning(
                "Callback data не содержит достаточно частей: %s", callback_data
            )
            return None

        return int(parts[index])
    except (ValueError, IndexError) as e:
        logger.warning("Ошибка при парсинге callback_data '%s': %s", callback_data, e)
        return None
    except Exception as e:
        logger.error(
            "Неожиданная ошибка при парсинге callback_data '%s': %s", callback_data, e
        )
        return None


def safe_extract_lot_id(callback_data: str) -> Optional[int]:
    """Безопасно извлекает ID лота из callback_data"""
    return safe_extract_id(callback_data, ":", 1)


def safe_extract_user_id(callback_data: str) -> Optional[int]:
    """Безопасно извлекает ID пользователя из callback_data"""
    return safe_extract_id(callback_data, ":", 1)


def safe_extract_complaint_id(callback_data: str) -> Optional[int]:
    """Безопасно извлекает ID жалобы из callback_data"""
    return safe_extract_id(callback_data, ":", 1)


def safe_extract_question_id(callback_data: str) -> Optional[int]:
    """Безопасно извлекает ID вопроса из callback_data"""
    return safe_extract_id(callback_data, ":", 1)
