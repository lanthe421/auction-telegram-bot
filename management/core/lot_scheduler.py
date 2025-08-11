"""
Сервис планирования публикации лотов
"""

import asyncio
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, Set

from database.db import SessionLocal
from database.models import Lot, LotStatus
from management.core.telegram_publisher_sync import telegram_publisher_sync

logger = logging.getLogger(__name__)


class LotScheduler:
    """Сервис для планирования публикации лотов"""

    def __init__(self):
        self.scheduled_lots: Dict[int, threading.Timer] = {}
        self.running = False

    def start(self):
        """Запускает планировщик"""
        self.running = True
        logger.info("Планировщик лотов запущен")

        # Запускаем планирование для всех одобренных лотов с будущим временем старта
        self.schedule_all_pending_lots()

    def stop(self):
        """Останавливает планировщик"""
        self.running = False
        # Отменяем все запланированные задачи
        for timer in self.scheduled_lots.values():
            timer.cancel()
        self.scheduled_lots.clear()
        logger.info("Планировщик лотов остановлен")

    def schedule_lot_publication(self, lot_id: int, start_time: datetime):
        """Планирует публикацию лота на указанное время"""
        if not self.running:
            return

        # Отменяем предыдущий таймер для этого лота, если есть
        if lot_id in self.scheduled_lots:
            self.scheduled_lots[lot_id].cancel()

        # Вычисляем задержку до времени старта (нормализуем к UTC)
        now = datetime.now(timezone.utc)
        start_utc = start_time
        if getattr(start_utc, "tzinfo", None) is None:
            start_utc = start_utc.replace(tzinfo=timezone.utc)
        else:
            start_utc = start_utc.astimezone(timezone.utc)
        delay = (start_utc - now).total_seconds()

        if delay <= 0:
            # Время уже наступило - публикуем сразу
            self.publish_lot(lot_id)
        else:
            # Планируем публикацию
            timer = threading.Timer(delay, self.publish_lot, args=[lot_id])
            timer.start()
            self.scheduled_lots[lot_id] = timer

            logger.info(
                f"Лот {lot_id} запланирован на публикацию в {start_utc.strftime('%d.%m.%Y %H:%M %Z')}"
            )

    def publish_lot(self, lot_id: int):
        """Публикует лот в канал"""
        try:
            # Проверяем, что лот все еще активен и не был опубликован
            db = SessionLocal()
            lot = (
                db.query(Lot)
                .filter(Lot.id == lot_id, Lot.status == LotStatus.ACTIVE)
                .first()
            )

            if lot and not lot.telegram_message_id:
                # Публикуем лот
                success = telegram_publisher_sync.publish_lot(lot_id)
                if success:
                    logger.info(f"Лот {lot_id} успешно опубликован в канал")
                else:
                    logger.error(f"Ошибка при публикации лота {lot_id}")
            else:
                logger.info(f"Лот {lot_id} уже опубликован или неактивен")

        except Exception as e:
            logger.error(f"Ошибка при публикации лота {lot_id}: {e}")
        finally:
            db.close()

        # Удаляем из запланированных
        if lot_id in self.scheduled_lots:
            del self.scheduled_lots[lot_id]

    def schedule_all_pending_lots(self):
        """Планирует публикацию всех одобренных лотов с будущим временем старта"""
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)

            # Находим все активные лоты с будущим временем старта
            pending_lots = (
                db.query(Lot)
                .filter(
                    Lot.status == LotStatus.ACTIVE,
                    Lot.start_time > now,
                    Lot.telegram_message_id.is_(None),  # Еще не опубликованы
                )
                .all()
            )

            for lot in pending_lots:
                self.schedule_lot_publication(lot.id, lot.start_time)

            logger.info(f"Запланировано {len(pending_lots)} лотов для публикации")

        except Exception as e:
            logger.error(f"Ошибка при планировании лотов: {e}")
        finally:
            db.close()

    def cancel_lot_publication(self, lot_id: int):
        """Отменяет запланированную публикацию лота"""
        if lot_id in self.scheduled_lots:
            self.scheduled_lots[lot_id].cancel()
            del self.scheduled_lots[lot_id]
            logger.info(f"Публикация лота {lot_id} отменена")


# Глобальный экземпляр планировщика
lot_scheduler = LotScheduler()
