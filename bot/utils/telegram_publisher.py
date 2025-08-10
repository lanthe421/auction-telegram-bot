import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import (
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
)
from sqlalchemy import update
from sqlalchemy.orm import Session

from bot.utils.lot_helpers import get_current_leader
from config.settings import BOT_TOKEN, BOT_USERNAME, TELEGRAM_GROUP_ID
from database.db import SessionLocal
from database.models import Bid, Lot, LotStatus, User

logger = logging.getLogger(__name__)


class TelegramPublisher:
    """Класс для публикации лотов в Telegram канал"""

    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.group_id = TELEGRAM_GROUP_ID
        self._published_lots = set()
        # Глобальная пауза редактирования канала (антифлуд)
        self.cooldown_until_ts: float = 0.0

    async def publish_lot(self, lot_id: int, retry_count: int = 3) -> bool:
        """Публикует лот в канал"""
        db = SessionLocal()
        message = None  # Инициализируем message

        try:
            lot = db.query(Lot).filter(Lot.id == lot_id).first()
            if not lot:
                logger.error(f"Лот {lot_id} не найден")
                return False

            seller = db.query(User).filter(User.id == lot.seller_id).first()
            if not seller:
                logger.error(f"Продавец для лота {lot_id} не найден")
                return False

            message_text = self._format_lot_message(lot, seller, db)
            keyboard = self._create_channel_keyboard(lot)

            images = []
            images_json = getattr(lot, "images", None)
            if images_json:
                try:
                    images = json.loads(images_json)
                    images = [img for img in images if os.path.exists(img)]
                except Exception as e:
                    logger.warning(f"Ошибка при парсинге изображений: {e}")

            if images and len(images) > 1:
                logger.info(
                    f"Публикация альбома: найдено {len(images)} файлов: {images}"
                )
                # Отправляем все изображения как альбом
                media = []
                for img_path in images:
                    if not os.path.exists(img_path):
                        logger.warning(f"Файл не найден: {img_path}")
                        continue
                    try:
                        media.append(InputMediaPhoto(media=FSInputFile(img_path)))
                    except Exception as e:
                        logger.warning(
                            f"Ошибка при загрузке изображения {img_path}: {e}"
                        )
                logger.info(
                    f"Формируем альбом из {len(media)} файлов: {[m.media for m in media]}"
                )
                try:
                    result = await self.bot.send_media_group(
                        chat_id=self.group_id, media=media
                    )
                    logger.info(f"Результат отправки альбома: {result}")
                except Exception as e:
                    logger.error(f"Ошибка при отправке альбома: {e}")
                    return False
                # После альбома отправляем описание и кнопки
                try:
                    message = await self.bot.send_message(
                        chat_id=self.group_id,
                        text=message_text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.error(f"Ошибка при отправке описания: {e}")
                    return False
            elif images:
                # Если только одно изображение — отправляем как раньше
                try:
                    with open(images[0], "rb") as photo_file:
                        message = await self.bot.send_photo(
                            chat_id=self.group_id,
                            photo=photo_file,
                            caption=message_text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                        )
                except Exception as e:
                    logger.error(f"Ошибка загрузки изображения {images[0]}: {e}")
                    return False
            else:
                message = await self.bot.send_message(
                    chat_id=self.group_id,
                    text=message_text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )

            if message:
                db.execute(
                    update(Lot)
                    .where(Lot.id == lot_id)
                    .values(telegram_message_id=message.message_id)
                )
                db.commit()
                self._published_lots.add(lot_id)
                return True
            return False

        except Exception as e:
            logger.error(f"Ошибка публикации: {e}")
            if retry_count > 0:
                await asyncio.sleep(2)
                return await self.publish_lot(lot_id, retry_count - 1)
            return False

        finally:
            db.close()

    async def edit_lot_message(
        self, lot_id: int, message_id: int, new_text: str
    ) -> bool:
        """Редактирует текст сообщения лота в канале."""
        try:
            if not new_text or not str(new_text).strip():
                new_text = "Обновление информации о лоте"
            try:
                await self.bot.edit_message_text(
                    chat_id=self.group_id,
                    message_id=message_id,
                    text=new_text,
                    parse_mode="HTML",
                )
                return True
            except Exception as inner:
                # Если сообщение без текста (например, фото с подписью), пробуем изменить подпись
                lower_inner = str(inner).lower()
                if (
                    "there is no text in the message to edit" in lower_inner
                    or "message to edit has no text" in lower_inner
                ):
                    await self.bot.edit_message_caption(
                        chat_id=self.group_id,
                        message_id=message_id,
                        caption=new_text,
                        parse_mode="HTML",
                    )
                    return True
                # Флуд-контроль
                if isinstance(inner, TelegramRetryAfter):
                    self.cooldown_until_ts = __import__("time").time() + float(
                        inner.retry_after
                    )
                    return False
                raise
        except Exception as e:
            # Игнорируем 'message is not modified'
            if "message is not modified" in str(e).lower():
                return True
            # Флуд-контроль
            if isinstance(e, TelegramRetryAfter):
                self.cooldown_until_ts = __import__("time").time() + float(
                    e.retry_after
                )
                return False
            # Если сообщение не найдено в канале — инвалидируем telegram_message_id, чтобы прекратить дальнейшие попытки
            if "message to edit not found" in str(e).lower():
                try:
                    db = SessionLocal()
                    lot = db.query(Lot).filter(Lot.id == lot_id).first()
                    if lot:
                        lot.telegram_message_id = None
                        db.commit()
                except Exception:
                    pass
                finally:
                    try:
                        db.close()
                    except Exception:
                        pass
                logger.warning(
                    f"Сообщение лота {lot_id} для редактирования не найдено. telegram_message_id сброшен."
                )
                return False
            logger.error(
                f"Ошибка при редактировании сообщения лота {lot_id} (msg_id={message_id}): {e}"
            )
            return False

    async def refresh_lot_message(self, lot_id: int) -> bool:
        """Переформирует текст лота и редактирует сообщение в канале (цена, лидер и т.д.)."""
        db = SessionLocal()
        try:
            lot = db.query(Lot).filter(Lot.id == lot_id).first()
            if not lot or not getattr(lot, "telegram_message_id", None):
                return False
            seller = db.query(User).filter(User.id == lot.seller_id).first()
            if not seller:
                return False
            new_text = self._format_lot_message(lot, seller, db)
            keyboard = self._create_channel_keyboard(lot)
            try:
                await self.bot.edit_message_text(
                    chat_id=self.group_id,
                    message_id=lot.telegram_message_id,
                    text=new_text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
                return True
            except Exception as e:
                lower_e = str(e).lower()
                if "message is not modified" in lower_e:
                    return True
                # Если это фото с подписью — редактируем подпись
                if (
                    "there is no text in the message to edit" in lower_e
                    or "message to edit has no text" in lower_e
                ):
                    try:
                        await self.bot.edit_message_caption(
                            chat_id=self.group_id,
                            message_id=lot.telegram_message_id,
                            caption=new_text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                        )
                        return True
                    except Exception as cap_err:
                        if "message is not modified" in str(cap_err).lower():
                            return True
                # Флуд-контроль
                if isinstance(e, TelegramRetryAfter):
                    self.cooldown_until_ts = __import__("time").time() + float(
                        e.retry_after
                    )
                    return False
                # Если сообщение не найдено в канале — инвалидируем telegram_message_id, чтобы больше не пытаться
                if "message to edit not found" in str(e).lower():
                    try:
                        lot.telegram_message_id = None
                        db.commit()
                    except Exception:
                        pass
                    logger.warning(
                        f"Сообщение лота {lot_id} для редактирования не найдено. telegram_message_id сброшен."
                    )
                    return False
                logger.error(
                    f"Ошибка обновления сообщения лота {lot_id} (msg_id={lot.telegram_message_id}): {e}"
                )
                return False
        finally:
            db.close()

    def _format_lot_message(self, lot: Lot, seller: User, db: Session) -> str:
        """Форматирует сообщение о лоте"""
        status = getattr(lot, "status", None)
        end_time = getattr(lot, "end_time", None)
        is_active = (
            status == LotStatus.ACTIVE and end_time and end_time > datetime.utcnow()
        )

        images_text = ""
        images_json = getattr(lot, "images", None)
        if images_json:
            try:
                images = json.loads(images_json)
                if images:
                    images_text = f"\n📸 Изображений: {len(images)}"
            except Exception:
                pass

        location = getattr(lot, "location", None)
        seller_link = getattr(lot, "seller_link", None)
        start_time = getattr(lot, "start_time", None)
        end_time = getattr(lot, "end_time", None)

        # Текущий лидер (маскированный) — учитываем только «свежие» ставки
        leader_name, leader_amount = get_current_leader(db, lot.id)

        return f"""
🏷️ <b>{getattr(lot, 'title', '')}</b>

📝 <b>Описание:</b>
{getattr(lot, 'description', '')}

💰 <b>Стартовая цена:</b> {getattr(lot, 'starting_price', 0):,.2f} ₽
💰 <b>Текущая цена:</b> {getattr(lot, 'current_price', 0):,.2f} ₽
📈 <b>Минимальная ставка:</b> {getattr(lot, 'min_bid_increment', 0):,.2f} ₽

 🥇 <b>Лидер:</b> {leader_name}{f" ({leader_amount:,.2f} ₽)" if leader_amount else ''}

👤 <b>Продавец:</b> {getattr(seller, 'first_name', '')}
{seller_link and f"\n🔗 Ссылка на продавца: {seller_link}" or ""}
{location and f"\n📍 Геолокация: {location}" or ""}

📊 <b>Ставок:</b> {len(getattr(lot, 'bids', []))}
⏰ <b>Начало:</b> {start_time.strftime('%d.%m.%Y %H:%M') if start_time else 'Немедленно'}
⏰ <b>Окончание:</b> {end_time.strftime('%d.%m.%Y %H:%M') if end_time else 'Не определено'}
{images_text}

{'🟢' if is_active else '🔴'} <b>Статус:</b> {'Активен' if is_active else 'Завершен'}
        """.strip()

    def _create_channel_keyboard(self, lot: Lot) -> InlineKeyboardMarkup:
        """Клавиатура для канала: только ссылка 'Открыть лот' в боте без callback."""
        deep_link = (
            f"https://t.me/{BOT_USERNAME}?start=lot_{lot.id}" if BOT_USERNAME else None
        )
        if deep_link:
            keyboard = [[InlineKeyboardButton(text="🔗 Открыть лот", url=deep_link)]]
            return InlineKeyboardMarkup(inline_keyboard=keyboard)
        # Если BOT_USERNAME не задан, возвращаем пустую клавиатуру
        return InlineKeyboardMarkup(inline_keyboard=[])

    async def close(self):
        """Закрывает соединение с ботом"""
        await self.bot.session.close()


telegram_publisher = TelegramPublisher()
