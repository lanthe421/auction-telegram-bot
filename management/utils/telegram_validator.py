#!/usr/bin/env python3
"""
Модуль для валидации Telegram ID
Базовая проверка формата без обращения к API
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class TelegramValidator:
    """Класс для валидации Telegram ID"""

    def __init__(self):
        """Инициализация валидатора"""
        pass

    def validate_telegram_id(self, telegram_id: int) -> Dict[str, Any]:
        """
        Проверяет формат Telegram ID

        Args:
            telegram_id: Telegram ID для проверки

        Returns:
            Dict с результатом проверки:
            {
                'valid': bool,
                'user_info': dict или None,
                'error': str или None
            }
        """
        return self._basic_validation(telegram_id)

    def _basic_validation(self, telegram_id: int) -> Dict[str, Any]:
        """
        Базовая валидация Telegram ID

        Args:
            telegram_id: Telegram ID для проверки

        Returns:
            Dict с результатом базовой проверки
        """
        # Проверяем, что ID положительный
        if telegram_id <= 0:
            return {
                "valid": False,
                "user_info": None,
                "error": "Telegram ID должен быть положительным числом",
            }

        # Проверяем, что ID не слишком большой
        if telegram_id > 999999999999999:
            return {
                "valid": False,
                "user_info": None,
                "error": "Telegram ID слишком большой",
            }

        return {
            "valid": True,
            "user_info": {"id": telegram_id, "first_name": "Пользователь"},
            "error": None,
        }

    def get_user_info(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """
        Получает базовую информацию о пользователе

        Args:
            telegram_id: Telegram ID пользователя

        Returns:
            Dict с информацией о пользователе или None
        """
        result = self.validate_telegram_id(telegram_id)
        return result.get("user_info") if result["valid"] else None

    def is_valid_telegram_id(self, telegram_id: int) -> bool:
        """
        Проверяет, является ли Telegram ID валидным

        Args:
            telegram_id: Telegram ID для проверки

        Returns:
            True если ID валидный, False иначе
        """
        result = self.validate_telegram_id(telegram_id)
        return result["valid"]


# Глобальный экземпляр валидатора
telegram_validator = TelegramValidator()


def validate_telegram_id(telegram_id: int) -> Dict[str, Any]:
    """
    Удобная функция для валидации Telegram ID

    Args:
        telegram_id: Telegram ID для проверки

    Returns:
        Dict с результатом проверки
    """
    return telegram_validator.validate_telegram_id(telegram_id)


def is_valid_telegram_id(telegram_id: int) -> bool:
    """
    Удобная функция для проверки валидности Telegram ID

    Args:
        telegram_id: Telegram ID для проверки

    Returns:
        True если ID валидный, False иначе
    """
    return telegram_validator.is_valid_telegram_id(telegram_id)
