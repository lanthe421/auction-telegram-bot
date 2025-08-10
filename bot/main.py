"""
Главный файл Telegram бота для аукционов
"""

import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config.logging import setup_logging
from config.settings import BOT_TOKEN, LOG_LEVEL
from database.db import close_db, init_db
from management.utils.cache_manager import start_cache_cleanup, stop_cache_cleanup
from management.utils.image_optimizer import media_manager
from management.utils.performance_monitor import (
    start_performance_monitoring,
    stop_performance_monitoring,
)

from .handlers import admin, auction, bids, payments, support, users

# Настройка логирования
setup_logging()
logger = logging.getLogger(__name__)

# Глобальные переменные
bot: Bot = None
dp: Dispatcher = None


@asynccontextmanager
async def lifespan():
    """Контекстный менеджер жизненного цикла приложения"""
    global bot, dp

    try:
        # Инициализация
        logger.info("Запуск бота...")

        # Инициализация БД
        init_db()
        logger.info("База данных инициализирована")

        # Создание бота и диспетчера
        bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)

        # Регистрация хендлеров
        await register_handlers()
        logger.info("Хендлеры зарегистрированы")

        # Запуск мониторинга производительности
        start_performance_monitoring(interval=60)
        logger.info("Мониторинг производительности запущен")

        # Запуск очистки кэша
        start_cache_cleanup(interval=300)  # 5 минут
        logger.info("Очистка кэша запущена")

        # Инициализация медиа менеджера
        await media_manager._async_init()
        logger.info("Медиа менеджер инициализирован")

        logger.info("Бот успешно запущен")
        yield

    except Exception as e:
        logger.error(f"Ошибка при запуске: {e}")
        raise
    finally:
        # Очистка ресурсов
        logger.info("Остановка бота...")

        # Остановка мониторинга
        stop_performance_monitoring()
        logger.info("Мониторинг производительности остановлен")

        # Остановка очистки кэша
        stop_cache_cleanup()
        logger.info("Очистка кэша остановлена")

        # Закрытие БД
        close_db()
        logger.info("База данных закрыта")

        # Закрытие бота
        if bot:
            await bot.session.close()
            logger.info("Сессия бота закрыта")


async def register_handlers():
    """Регистрирует все хендлеры"""
    # Основные хендлеры
    dp.include_router(users.router)
    dp.include_router(auction.router)
    dp.include_router(bids.router)

    # Административные хендлеры
    dp.include_router(admin.router)
    dp.include_router(payments.router)
    dp.include_router(support.router)


async def main():
    """Главная функция"""
    async with lifespan():
        try:
            # Запуск бота
            await dp.start_polling(bot)
        except KeyboardInterrupt:
            logger.info("Получен сигнал остановки")
        except Exception as e:
            logger.error(f"Критическая ошибка: {e}")
            raise


def signal_handler(signum, frame):
    """Обработчик сигналов для graceful shutdown"""
    logger.info(f"Получен сигнал {signum}, начинаю остановку...")
    if dp:
        asyncio.create_task(dp.stop_polling())
    sys.exit(0)


if __name__ == "__main__":
    # Регистрация обработчиков сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Запуск основного цикла
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске: {e}")
        sys.exit(1)
