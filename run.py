#!/usr/bin/env python3
"""
Комплексный запуск системы управления аукционом
"""

import asyncio
import logging
import os
import signal
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Thread

# Добавляем корневую директорию в путь Python
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Безопасный вывод Unicode в Windows-консоли
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from config.settings import get_project_root, validate_settings
from management.utils.cache_manager import start_cache_cleanup, stop_cache_cleanup
from management.utils.performance_monitor import (
    start_performance_monitoring,
    stop_performance_monitoring,
)


# Настройка логирования
def setup_logging():
    """Настраивает систему логирования"""
    log_dir = get_project_root() / "logs"
    log_dir.mkdir(exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "system.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


# Глобальные переменные для управления процессами
bot_process = None
management_process = None
is_shutting_down = False


def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения"""
    global is_shutting_down
    print(f"\n🛑 Получен сигнал {signum}, завершаем работу...")
    is_shutting_down = True

    # Останавливаем мониторинг
    stop_performance_monitoring()
    stop_cache_cleanup()

    # Завершаем процессы
    if bot_process:
        bot_process.cancel()
    if management_process:
        management_process.cancel()

    sys.exit(0)


@asynccontextmanager
async def startup_shutdown():
    """Контекстный менеджер для запуска и завершения"""
    print("🚀 Инициализация системы...")

    # Запускаем мониторинг производительности
    start_performance_monitoring(interval=60)
    start_cache_cleanup(interval=300)

    print("✅ Система инициализирована")

    try:
        yield
    finally:
        print("🛑 Завершение работы системы...")
        stop_performance_monitoring()
        stop_cache_cleanup()
        print("✅ Система завершена")


async def run_bot():
    """Запускает Telegram бота"""
    try:
        from bot.main import main as bot_main
        from bot.utils.notifications import start_notification_service

        print("🤖 Запуск Telegram бота...")

        # Запускаем сервис уведомлений в отдельной задаче
        notification_task = asyncio.create_task(start_notification_service())
        print("🔔 Сервис уведомлений запущен")

        # Запускаем основную функцию бота
        await bot_main()

        # Отменяем задачу уведомлений при завершении
        notification_task.cancel()

    except Exception as e:
        print(f"❌ Ошибка при запуске бота: {e}")
        logging.error(f"Ошибка при запуске бота: {e}")


async def run_management():
    """Запускает систему управления"""
    try:
        from management.main import main as management_main

        print("💻 Запуск системы управления...")
        await asyncio.to_thread(management_main)
    except Exception as e:
        print(f"❌ Ошибка при запуске системы управления: {e}")
        logging.error(f"Ошибка при запуске системы управления: {e}")


async def health_check():
    """Проверка здоровья системы"""
    while not is_shutting_down:
        try:
            # Проверяем состояние основных компонентов
            from database.db import health_check as db_health_check

            db_healthy = db_health_check()

            if not db_healthy:
                print("⚠️  Предупреждение: проблемы с базой данных")
                logging.warning("Проблемы с базой данных")

            await asyncio.sleep(30)  # Проверка каждые 30 секунд

        except Exception as e:
            logging.error(f"Ошибка в health check: {e}")
            await asyncio.sleep(60)


async def run_all():
    """Запускает все компоненты системы"""
    print("🚀 Комплексный запуск системы управления аукционом...")
    print()

    # Проверяем настройки
    errors = validate_settings()
    if errors:
        print("❌ Ошибки в конфигурации:")
        for error in errors:
            print(f"   • {error}")
        print("\nПожалуйста, исправьте ошибки в настройках и перезапустите систему.")
        return

    print("📋 Запускаемые компоненты:")
    print("   ✅ Telegram бот")
    print("   ✅ Система управления")
    print("   ✅ Сервис проверки аукционов")
    print("   ✅ Мониторинг производительности")
    print("   ✅ Система кэширования")
    print()
    print("👥 Для входа используйте:")
    print("   • Модератор: Telegram Username moderator, роль 'Модератор'")
    print("   • Супер-админ: Telegram Username superadmin, роль 'Супер-администратор'")
    print()
    print("💡 Для регистрации нового пользователя используйте форму регистрации")
    print("🔍 Мониторинг производительности активен")
    print()

    async with startup_shutdown():
        # Запускаем все компоненты параллельно
        tasks = [
            asyncio.create_task(run_bot()),
            asyncio.create_task(run_management()),
            asyncio.create_task(health_check()),
        ]

        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            print(f"❌ Критическая ошибка: {e}")
            logging.error(f"Критическая ошибка: {e}")
        finally:
            # Отменяем все задачи
            for task in tasks:
                if not task.done():
                    task.cancel()


def main():
    """Главная функция"""
    # Настраиваем обработчики сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Настраиваем логирование
    setup_logging()

    try:
        # Запускаем асинхронную систему
        asyncio.run(run_all())
    except KeyboardInterrupt:
        print("\n🛑 Система остановлена пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        logging.error(f"Критическая ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
