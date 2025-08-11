"""
Модуль для публикации лотов в Telegram группы
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto

from config.settings import (
    BOT_TOKEN,
    BOT_USERNAME,
    DEBUG,
    TELEGRAM_API_TIMEOUT,
    TELEGRAM_GROUP_ID,
    TELEGRAM_RETRY_DELAY,
)
from database.db import SessionLocal
from database.models import Bid, Lot, LotStatus, User

logger = logging.getLogger(__name__)


class TelegramPublisher:
    """Класс для публикации лотов в Telegram канал"""

    def __init__(self):
        self.bot = None
        self.group_id = TELEGRAM_GROUP_ID
        self._published_lots = set()  # Кэш опубликованных лотов

    def _get_bot(self):
        """Получает или создает экземпляр бота"""
        if self.bot is None:
            self.bot = Bot(token=BOT_TOKEN)
        return self.bot

    async def publish_lot(self, lot_id: int, retry_count: int = 3) -> bool:
        """Публикует лот в Telegram канал с повторными попытками"""

        # Проверяем, не был ли лот уже опубликован
        if lot_id in self._published_lots:
            logger.info(f"Лот {lot_id} уже был опубликован")
            return True

        for attempt in range(retry_count):
            try:
                db = SessionLocal()
                lot = db.query(Lot).filter(Lot.id == lot_id).first()

                if not lot:
                    logger.error(f"Лот {lot_id} не найден")
                    return False

                if lot.status != LotStatus.ACTIVE:
                    logger.error(f"Лот {lot_id} не активен (статус: {lot.status})")
                    return False

                # Получаем информацию о продавце
                seller = db.query(User).filter(User.id == lot.seller_id).first()
                seller_name = seller.first_name if seller else "Неизвестно"

                # Создаем текст сообщения
                message_text = self.create_lot_message(lot, seller_name)

                # Создаем клавиатуру
                keyboard = self.create_lot_keyboard(lot.id)

                # Публикуем в канал
                bot = self._get_bot()
                message = await bot.send_message(
                    chat_id=self.group_id,
                    text=message_text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )

                # Сохраняем ID сообщения в базе данных
                lot.telegram_message_id = message.message_id
                db.commit()

                # Добавляем в кэш опубликованных
                self._published_lots.add(lot_id)

                logger.info(
                    f"Лот {lot_id} успешно опубликован в канал (попытка {attempt + 1})"
                )
                return True

            except TelegramRetryAfter as e:
                wait_time = e.retry_after
                logger.warning(f"Превышен лимит API, ожидаем {wait_time} секунд")
                await asyncio.sleep(wait_time)

            except TelegramAPIError as e:
                logger.error(
                    f"Ошибка Telegram API при публикации лота {lot_id} (попытка {attempt + 1}): {e}"
                )
                if attempt < retry_count - 1:
                    await asyncio.sleep(TELEGRAM_RETRY_DELAY)

            except Exception as e:
                logger.error(
                    f"Неожиданная ошибка при публикации лота {lot_id} (попытка {attempt + 1}): {e}"
                )
                if attempt < retry_count - 1:
                    await asyncio.sleep(TELEGRAM_RETRY_DELAY)

            finally:
                db.close()

        logger.error(
            f"Не удалось опубликовать лот {lot_id} после {retry_count} попыток"
        )
        return False

    def create_lot_message(self, lot: Lot, seller_name: str) -> str:
        """Создает текст сообщения для лота"""
        # Форматируем время по МСК
        try:
            from bot.utils.time_utils import utc_to_moscow

            start_time = (
                utc_to_moscow(lot.start_time).strftime("%d.%m.%Y в %H:%M")
                if lot.start_time
                else "Немедленно"
            )
            end_time = (
                utc_to_moscow(lot.end_time).strftime("%d.%m.%Y в %H:%M")
                if lot.end_time
                else "Не определено"
            )
        except Exception:
            start_time = (
                lot.start_time.strftime("%d.%m.%Y в %H:%M")
                if lot.start_time
                else "Немедленно"
            )
            end_time = (
                lot.end_time.strftime("%d.%m.%Y в %H:%M")
                if lot.end_time
                else "Не определено"
            )

        # Определяем тип документа
        doc_type_text = {
            "standard": "Стандартный лот",
            "jewelry": "Ювелирное изделие",
            "historical": "Историческая ценность",
        }.get(lot.document_type.value, "Стандартный лот")

        # Добавляем информацию о текущих ставках
        db = SessionLocal()
        try:
            current_bids = db.query(Bid).filter(Bid.lot_id == lot.id).count()
            highest_bid = (
                db.query(Bid)
                .filter(Bid.lot_id == lot.id)
                .order_by(Bid.amount.desc())
                .first()
            )
            current_price = highest_bid.amount if highest_bid else lot.starting_price
        except Exception as e:
            logger.error(f"Ошибка при получении информации о ставках: {e}")
            current_bids = 0
            current_price = lot.starting_price
        finally:
            db.close()

        message = f"""
🏛️ <b>НОВЫЙ ЛОТ #{lot.id}</b>

📦 <b>{lot.title}</b>

📝 <b>Описание:</b>
{lot.description}

💰 <b>Стартовая цена:</b> {lot.starting_price:,.2f} ₽
💎 <b>Текущая цена:</b> {current_price:,.2f} ₽
📊 <b>Количество ставок:</b> {current_bids}

👤 <b>Продавец:</b> {seller_name}

📍 <b>Геолокация:</b> {lot.location or 'Не указана'}

📅 <b>Время старта:</b> {start_time}
⏰ <b>Время окончания:</b> {end_time}

📄 <b>Тип документа:</b> {doc_type_text}

🔗 <b>Ссылка на продавца:</b> {lot.seller_link or 'Не указана'}

💡 <b>Как участвовать:</b>
• Нажмите кнопку "Сделать ставку" ниже
• Или перейдите в бота @{BOT_USERNAME}
• Минимальный шаг ставки: {lot.min_bid_increment:,.2f} ₽
        """

        return message.strip()

    def create_lot_keyboard(self, lot_id: int) -> InlineKeyboardMarkup:
        """Клавиатура для канала: контакт/время + ссылка 'Открыть лот'."""
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📞 Связаться с продавцом",
                        callback_data=f"contact_seller_{lot_id}",
                    ),
                    InlineKeyboardButton(
                        text="⏰ Время окончания",
                        callback_data=f"time_remaining_{lot_id}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="🔗 Открыть лот",
                        url=f"https://t.me/{BOT_USERNAME}?start=lot_{lot_id}",
                    )
                ],
            ]
        )
        return keyboard

    async def update_lot_status(self, lot_id: int, new_status: str) -> bool:
        """Обновляет статус лота в канале"""
        try:
            db = SessionLocal()
            lot = db.query(Lot).filter(Lot.id == lot_id).first()

            if not lot:
                logger.error(f"Лот {lot_id} не найден")
                return False

            status_messages = {
                "sold": f"🏆 Лот #{lot_id} продан!",
                "cancelled": f"❌ Лот #{lot_id} отменен",
                "expired": f"⏰ Лот #{lot_id} истек без ставок",
            }

            message_text = status_messages.get(
                new_status, f"📢 Лот #{lot_id} - {new_status}"
            )

            bot = self._get_bot()
            await bot.send_message(
                chat_id=self.group_id,
                text=message_text,
                parse_mode="HTML",
            )

            logger.info(f"Статус лота {lot_id} обновлен: {new_status}")
            return True

        except Exception as e:
            logger.error(f"Ошибка при обновлении статуса лота {lot_id}: {e}")
            return False
        finally:
            db.close()

    async def edit_lot_message(
        self, lot_id: int, message_id: int, new_text: str
    ) -> bool:
        """Редактирует сообщение о лоте в канале"""
        try:
            bot = self._get_bot()
            await bot.edit_message_text(
                chat_id=self.group_id,
                message_id=message_id,
                text=new_text,
                parse_mode="HTML",
            )
            logger.info(f"Сообщение о лоте {lot_id} отредактировано")
            return True
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения о лоте {lot_id}: {e}")
            return False

    async def send_lot_deleted_message(
        self, lot_id: int, lot_title: str, had_bids: bool
    ) -> bool:
        """Отправляет сообщение об удалении лота"""
        try:
            if had_bids:
                message_text = f"""
❌ <b>ЛОТ УДАЛЕН</b>

📦 <b>Лот #{lot_id}: {lot_title}</b>

⚠️ <b>Аукцион завершен досрочно</b>
📊 <b>Были сделаны ставки</b>

💡 <b>Причина:</b> Лот удален продавцом
                """
            else:
                message_text = f"""
❌ <b>ЛОТ УДАЛЕН</b>

📦 <b>Лот #{lot_id}: {lot_title}</b>

⚠️ <b>Аукцион завершен</b>
📊 <b>Победителей нет</b>

💡 <b>Причина:</b> Лот удален продавцом
                """

            bot = self._get_bot()
            await bot.send_message(
                chat_id=self.group_id,
                text=message_text.strip(),
                parse_mode="HTML",
            )

            logger.info(f"Сообщение об удалении лота {lot_id} отправлено")
            return True
        except Exception as e:
            logger.error(
                f"Ошибка при отправке сообщения об удалении лота {lot_id}: {e}"
            )
            return False

    async def publish_winner_announcement(
        self, lot_id: int, winner_id: int, final_price: float
    ) -> bool:
        """Публикует объявление о победителе"""
        try:
            db = SessionLocal()
            lot = db.query(Lot).filter(Lot.id == lot_id).first()
            winner = db.query(User).filter(User.id == winner_id).first()

            if not lot or not winner:
                logger.error(f"Лот {lot_id} или победитель {winner_id} не найден")
                return False

            winner_name = f"{winner.first_name} {winner.last_name or ''}".strip()

            message = f"""
🏆 <b>ПОБЕДИТЕЛЬ АУКЦИОНА!</b>

📦 <b>Лот:</b> {lot.title}
👤 <b>Победитель:</b> {winner_name}
💰 <b>Финальная цена:</b> {final_price:,.2f} ₽

🎉 Поздравляем победителя!
📞 Свяжитесь с продавцом для завершения сделки.

#аукцион #победитель
            """

            bot = self._get_bot()
            await bot.send_message(
                chat_id=self.group_id,
                text=message.strip(),
                parse_mode="HTML",
            )

            logger.info(f"Объявление о победителе лота {lot_id} опубликовано")
            return True

        except Exception as e:
            logger.error(
                f"Ошибка при публикации объявления о победителе лота {lot_id}: {e}"
            )
            return False
        finally:
            db.close()

    async def check_and_publish_scheduled_lots(self) -> List[int]:
        """Проверяет и публикует запланированные лоты"""
        published_lots = []

        try:
            db = SessionLocal()
            current_time = datetime.now()

            # Находим лоты, которые нужно опубликовать
            lots_to_publish = (
                db.query(Lot)
                .filter(
                    Lot.status == LotStatus.PENDING,
                    Lot.start_time <= current_time,
                    Lot.approved_by.isnot(None),  # Только одобренные лоты
                )
                .all()
            )

            for lot in lots_to_publish:
                # Активируем лот
                lot.status = LotStatus.ACTIVE
                db.commit()

                # Публикуем в канал
                if await self.publish_lot(lot.id):
                    published_lots.append(lot.id)
                    logger.info(f"Запланированный лот {lot.id} опубликован")

        except Exception as e:
            logger.error(f"Ошибка при проверке запланированных лотов: {e}")
        finally:
            db.close()

        return published_lots

    async def check_and_close_expired_lots(self) -> List[int]:
        """Проверяет и закрывает истекшие лоты"""
        closed_lots = []

        try:
            db = SessionLocal()
            current_time = datetime.now()

            # Находим активные лоты, время которых истекло
            expired_lots = (
                db.query(Lot)
                .filter(Lot.status == LotStatus.ACTIVE, Lot.end_time <= current_time)
                .all()
            )

            for lot in expired_lots:
                # Проверяем, есть ли ставки
                highest_bid = (
                    db.query(Bid)
                    .filter(Bid.lot_id == lot.id)
                    .order_by(Bid.amount.desc())
                    .first()
                )

                if highest_bid:
                    # Есть ставки - лот продан
                    lot.status = LotStatus.SOLD
                    lot.current_price = highest_bid.amount

                    # Публикуем объявление о победителе
                    await self.publish_winner_announcement(
                        lot.id, highest_bid.bidder_id, highest_bid.amount
                    )

                    logger.info(f"Лот {lot.id} продан за {highest_bid.amount:,.2f} ₽")
                else:
                    # Нет ставок - лот истек
                    lot.status = LotStatus.EXPIRED
                    await self.update_lot_status(lot.id, "expired")
                    logger.info(f"Лот {lot.id} истек без ставок")

                closed_lots.append(lot.id)

            db.commit()

        except Exception as e:
            logger.error(f"Ошибка при проверке истекших лотов: {e}")
        finally:
            db.close()

        return closed_lots

    async def close(self):
        """Закрывает соединение с ботом"""
        try:
            if self.bot:
                await self.bot.session.close()
                self.bot = None
            logger.info("Telegram Publisher закрыт")
        except Exception as e:
            logger.error(f"Ошибка при закрытии Telegram Publisher: {e}")

    def clear_cache(self):
        """Очищает кэш опубликованных лотов"""
        self._published_lots.clear()
        logger.info("Кэш опубликованных лотов очищен")


# Глобальный экземпляр для использования в других модулях
telegram_publisher = TelegramPublisher()
