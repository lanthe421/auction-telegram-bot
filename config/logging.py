"""
Настройка логирования для системы
"""

import logging
import logging.config
import os
from pathlib import Path

from config.settings import LOG_FILE, LOG_LEVEL, get_logs_path


def setup_logging():
    """Настраивает логирование для всей системы"""
    try:
        # Создаем папку для логов если её нет
        logs_path = get_logs_path()
        logs_path.mkdir(exist_ok=True)

        # Путь к файлу логов
        log_file_path = logs_path / LOG_FILE

        # Базовая конфигурация логирования
        logging.basicConfig(
            level=getattr(logging, LOG_LEVEL.upper()),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler(log_file_path, encoding="utf-8"),
                logging.StreamHandler(),  # Вывод в консоль
            ],
        )

        # Настраиваем логирование для сторонних библиотек
        logging.getLogger("aiogram").setLevel(logging.INFO)
        logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)

        # Логируем успешную настройку
        logger = logging.getLogger(__name__)
        logger.info(
            f"Логирование настроено. Уровень: {LOG_LEVEL}, файл: {log_file_path}"
        )

    except Exception as e:
        # Если что-то пошло не так, используем базовую настройку
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        logging.error(f"Ошибка при настройке логирования: {e}")


def get_logger(name: str) -> logging.Logger:
    """Возвращает логгер с указанным именем"""
    return logging.getLogger(name)


def set_log_level(level: str):
    """Устанавливает уровень логирования для всех логгеров"""
    try:
        log_level = getattr(logging, level.upper())
        logging.getLogger().setLevel(log_level)

        # Устанавливаем уровень для всех модулей
        for logger_name in logging.root.manager.loggerDict:
            logging.getLogger(logger_name).setLevel(log_level)

    except Exception as e:
        logging.error(f"Ошибка при установке уровня логирования: {e}")

