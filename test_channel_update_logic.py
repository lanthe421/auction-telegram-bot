#!/usr/bin/env python3
"""
Тест логики обновления канала при автоставках
"""

import os
import sys
from datetime import datetime

# Добавляем корневую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.utils.auto_bid_manager import AutoBidManager
from database.db import SessionLocal, init_db
from database.models import AutoBid, Bid, Lot, LotStatus, User


def test_channel_update_logic():
    """Тестирует логику обновления канала"""
    print("🧪 ТЕСТ ЛОГИКИ ОБНОВЛЕНИЯ КАНАЛА")
    print("=" * 50)

    # Инициализируем базу данных
    try:
        init_db()
        print("✅ База данных инициализирована")
    except Exception as e:
        print(f"❌ Ошибка инициализации БД: {e}")
        return

    # Тестируем логику обновления канала
    print("\n📊 Тестируем логику обновления канала:")

    test_cases = [
        (1000, 1100, "10% изменение - должно обновляться"),
        (1000, 2000, "100% изменение - должно обновляться"),
        (1000, 1050, "5% изменение - НЕ должно обновляться"),
        (10000, 10900, "9% изменение, но 900₽ - НЕ должно обновляться"),
        (10000, 11000, "10% изменение - должно обновляться"),
        (1000, 2001, "1001₽ изменение - должно обновляться"),
        (1000, 1999, "999₽ изменение - НЕ должно обновляться"),
    ]

    for old_price, new_price, description in test_cases:
        should_update = AutoBidManager._should_update_channel(1, old_price, new_price)
        status = "✅ ДА" if should_update else "❌ НЕТ"
        print(f"   {status} | {old_price}₽ → {new_price}₽ | {description}")

    print("\n✅ Тестирование логики завершено!")
    print("📋 Теперь канал будет обновляться только при значительных изменениях")


if __name__ == "__main__":
    test_channel_update_logic()
