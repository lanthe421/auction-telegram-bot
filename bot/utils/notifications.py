"""
Система уведомлений для аукционного бота
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.utils.telegram_publisher import telegram_publisher
from bot.utils.time_utils import get_moscow_time, utc_to_moscow
from config.settings import BOT_TOKEN, NOTIFICATION_INTERVAL_MINUTES
from database.db import SessionLocal
from database.models import (
    Bid,
    Lot,
    LotStatus,
    Payment,
    SupportQuestion,
    User,
    UserRole,
)

logger = logging.getLogger(__name__)


class NotificationService:
    """Сервис уведомлений для аукционного бота"""

    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.notification_interval = NOTIFICATION_INTERVAL_MINUTES
        # Множество для отслеживания уже обработанных лотов
        self.processed_lots: Set[int] = set()
        # Кэш планировок напоминаний: (lot_id, label)
        self._scheduled_reminders: Set[Tuple[int, str]] = set()
        # Карта последних сообщений по теме, чтобы редактировать, а не слать новые: (user_id, topic) -> (message_id, last_text)
        self._user_topic_last: Dict[Tuple[int, str], Tuple[int, str]] = {}

    async def send_notification(
        self,
        user_id: int,
        message: str,
        keyboard: Optional[InlineKeyboardMarkup] = None,
        *,
        topic: Optional[str] = None,
        silent: bool = True,
    ) -> bool:
        """
        Отправляет уведомление пользователю

        Args:
            user_id: ID пользователя
            message: Текст сообщения
            keyboard: Клавиатура (опционально)

        Returns:
            bool: True если отправка успешна
        """
        try:
            # Учитываем настройку отключения уведомлений
            db = SessionLocal()
            try:
                user = db.query(User).filter(User.telegram_id == user_id).first()
                if user and getattr(user, "notifications_enabled", True) is False:
                    return False
            finally:
                db.close()

            # Добавляем кнопку подтверждения чтения, которая запустит удаление через 5 минут
            try:
                ack_button = InlineKeyboardButton(
                    text="✅ Прочитал (удалить через 5 минут)",
                    callback_data="acknowledge",
                )
                if keyboard and getattr(keyboard, "inline_keyboard", None):
                    combined_keyboard = InlineKeyboardMarkup(
                        inline_keyboard=keyboard.inline_keyboard + [[ack_button]]
                    )
                else:
                    combined_keyboard = InlineKeyboardMarkup(
                        inline_keyboard=[[ack_button]]
                    )
            except Exception:
                combined_keyboard = keyboard

            # Если задана тема — пробуем редактировать предыдущее сообщение, чтобы не засорять чат
            if topic:
                key = (user_id, topic)
                prev = self._user_topic_last.get(key)
                if prev and prev[0]:
                    try:
                        await self.bot.edit_message_text(
                            chat_id=user_id,
                            message_id=prev[0],
                            text=message,
                            reply_markup=combined_keyboard,
                            parse_mode="HTML",
                        )
                        self._user_topic_last[key] = (prev[0], message)
                        logger.info(
                            f"Уведомление обновлено (topic={topic}) пользователю {user_id}"
                        )
                        return True
                    except Exception:
                        # Если редактирование не удалось (нет сообщения/другая ошибка) — отправим новое
                        pass

            sent = await self.bot.send_message(
                chat_id=user_id,
                text=message,
                reply_markup=combined_keyboard,
                parse_mode="HTML",
                disable_notification=silent,
            )
            if topic:
                self._user_topic_last[(user_id, topic)] = (sent.message_id, message)
            logger.info(f"Уведомление отправлено пользователю {user_id}")
            return True
        except Exception as e:
            error_msg = str(e).lower()
            # Не логируем ошибки для несуществующих пользователей как критические
            if "chat not found" in error_msg or "user not found" in error_msg:
                logger.debug(
                    f"Пользователь {user_id} не найден в Telegram (возможно, тестовый ID)"
                )
            else:
                logger.error(
                    f"Ошибка при отправке уведомления пользователю {user_id}: {e}"
                )
            return False

    async def notify_new_bid(
        self, lot_id: int, bid_amount: float, bidder_name: str
    ) -> None:
        """Уведомляет о новой ставке"""
        db = SessionLocal()
        try:
            lot = db.query(Lot).filter(Lot.id == lot_id).first()
            if not lot:
                return

            # Уведомляем продавца (обновляем одно сообщение по теме, без звука)
            seller = db.query(User).filter(User.id == lot.seller_id).first()
            if seller:
                message = f"""
💰 <b>Новая ставка!</b>

🏷️ Лот: {lot.title}
💰 Сумма: {bid_amount:,.2f} ₽
👤 Ставщик: {bidder_name}
📅 Время: {datetime.now().strftime('%H:%M')}
                """
                await self.send_notification(
                    seller.telegram_id,
                    message.strip(),
                    topic=f"lot:{lot_id}:seller_updates",
                    silent=True,
                )

            # Больше не уведомляем всех участников о каждой новой ставке, чтобы не засорять чат

        except Exception as e:
            logger.error(f"Ошибка при уведомлении о новой ставке: {e}")
        finally:
            db.close()

    async def notify_auction_ending(self, lot_id: int, hours_left: int) -> None:
        """Уведомляет о скором окончании аукциона. Если до конца меньше часа, показывает минуты."""
        db = SessionLocal()
        try:
            lot = db.query(Lot).filter(Lot.id == lot_id).first()
            if not lot:
                return

            # Уведомляем всех участников
            participants = (
                db.query(Bid).filter(Bid.lot_id == lot_id).distinct(Bid.bidder_id).all()
            )
            # Высчитываем формат оставшегося времени
            left_seconds = 0
            try:
                now = get_moscow_time().replace(tzinfo=None)
                left_seconds = (
                    max(int((lot.end_time - now).total_seconds()), 0)
                    if lot.end_time
                    else 0
                )
            except Exception:
                left_seconds = 0

            if left_seconds >= 3600:
                left_str = f"{left_seconds // 3600} ч."
            elif left_seconds > 0:
                left_str = f"{max(left_seconds // 60, 1)} мин"
            else:
                left_str = "меньше минуты"

            for bid in participants:
                bidder = db.query(User).filter(User.id == bid.bidder_id).first()
                if bidder:
                    message = f"""
⏰ <b>Аукцион скоро закончится!</b>

🏷️ {lot.title}
💰 Текущая цена: {lot.current_price:,.2f} ₽
🕐 Осталось: {left_str}
🎯 Сделайте последнюю ставку!
                    """
                    await self.send_notification(bidder.telegram_id, message.strip())

        except Exception as e:
            logger.error(f"Ошибка при уведомлении об окончании аукциона: {e}")
        finally:
            db.close()

    async def notify_auction_winner(
        self, lot_id: int, winner_id: int, final_price: float
    ) -> None:
        """Уведомляет победителя аукциона"""
        db = SessionLocal()
        try:
            lot = db.query(Lot).filter(Lot.id == lot_id).first()
            winner = db.query(User).filter(User.id == winner_id).first()
            seller = db.query(User).filter(User.id == lot.seller_id).first()

            if lot and winner and seller:
                message = f"""
🏆 <b>Поздравляем! Вы выиграли аукцион!</b>

🏷️ Лот: {lot.title}
💰 Цена: {final_price:,.2f} ₽
📅 Дата: {datetime.now().strftime('%d.%m.%Y')}

👤 Продавец: {seller.first_name}
📞 Свяжитесь с продавцом для завершения сделки!
                """

                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="📞 Контакт продавца",
                                callback_data=f"seller_contact:{lot_id}",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text="📋 Детали лота",
                                callback_data=f"lot_details:{lot_id}",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text="📄 Скачать документ",
                                callback_data=f"download_transfer_doc:{lot_id}",
                            )
                        ],
                    ]
                )

                await self.send_notification(
                    winner.telegram_id, message.strip(), keyboard
                )

        except Exception as e:
            logger.error(f"Ошибка при уведомлении победителя: {e}")
        finally:
            db.close()

    async def notify_lot_approved(self, lot_id: int, seller_id: int) -> None:
        """Уведомляет о одобрении лота"""
        db = SessionLocal()
        try:
            lot = db.query(Lot).filter(Lot.id == lot_id).first()
            seller = db.query(User).filter(User.id == seller_id).first()

            if lot and seller:
                message = f"""
✅ <b>Ваш лот одобрен!</b>

🏷️ {lot.title}
📅 Публикация: {lot.start_time.strftime('%d.%m.%Y в %H:%M') if lot.start_time else 'Немедленно'}
💰 Стартовая цена: {lot.starting_price:,.2f} ₽

🎯 Лот будет опубликован в назначенное время!
                """
                await self.send_notification(seller.telegram_id, message.strip())

        except Exception as e:
            logger.error(f"Ошибка при уведомлении об одобрении лота: {e}")
        finally:
            db.close()

    async def notify_lot_rejected(
        self, lot_id: int, seller_id: int, reason: str
    ) -> None:
        """Уведомляет об отклонении лота"""
        db = SessionLocal()
        try:
            lot = db.query(Lot).filter(Lot.id == lot_id).first()
            seller = db.query(User).filter(User.id == seller_id).first()

            if lot and seller:
                message = f"""
❌ <b>Лот отклонен модератором</b>

🏷️ {lot.title}
📝 Причина: {reason}

🔄 Создайте новый лот с учетом замечаний
                """
                await self.send_notification(seller.telegram_id, message.strip())

        except Exception as e:
            logger.error(f"Ошибка при уведомлении об отклонении лота: {e}")
        finally:
            db.close()

    async def notify_complaint_received(
        self, complaint_id: int, complainant_id: int
    ) -> None:
        """Уведомляет о получении жалобы"""
        db = SessionLocal()
        try:
            complainant = db.query(User).filter(User.id == complainant_id).first()
            if complainant:
                message = f"""
📝 <b>Жалоба принята</b>

✅ Ваша жалоба получена и передана в службу поддержки
⏰ Рассмотрение займет до 24 часов

📞 Мы свяжемся с вами по результатам рассмотрения
                """
                await self.send_notification(complainant.telegram_id, message.strip())

        except Exception as e:
            logger.error(f"Ошибка при уведомлении о жалобе: {e}")
        finally:
            db.close()

    async def notify_support_staff(
        self, message: str, keyboard: Optional[InlineKeyboardMarkup] = None
    ) -> None:
        """Уведомляет персонал поддержки"""
        db = SessionLocal()
        try:
            support_users = db.query(User).filter(User.role == UserRole.SUPPORT).all()
            for user in support_users:
                await self.send_notification(user.telegram_id, message, keyboard)

        except Exception as e:
            logger.error(f"Ошибка при уведомлении персонала поддержки: {e}")
        finally:
            db.close()

    async def check_ending_auctions(self) -> None:
        """Проверяет аукционы, которые скоро закончатся (в пределах часа)"""
        db = SessionLocal()
        try:
            now = get_moscow_time()
            ending_soon = (
                db.query(Lot)
                .filter(
                    Lot.status == LotStatus.ACTIVE,
                    Lot.end_time > now.replace(tzinfo=None),
                    Lot.end_time <= (now + timedelta(hours=1)).replace(tzinfo=None),
                )
                .all()
            )

            for lot in ending_soon:
                # Конвертируем время из базы данных в московское время
                lot_moscow_time = utc_to_moscow(lot.end_time)
                hours_left = int((lot_moscow_time - now).total_seconds() / 3600)
                await self.notify_auction_ending(lot.id, hours_left)

        except Exception as e:
            logger.error(f"Ошибка при проверке заканшивающихся аукционов: {e}")
        finally:
            db.close()

    async def notify_auction_extended(
        self, lot_id: int, old_end_time: datetime, new_end_time: datetime
    ) -> None:
        """Уведомляет о продлении аукциона"""
        db = SessionLocal()
        try:
            lot = db.query(Lot).filter(Lot.id == lot_id).first()
            if not lot:
                return

            # Уведомляем всех участников
            participants = (
                db.query(Bid).filter(Bid.lot_id == lot_id).distinct(Bid.bidder_id).all()
            )

            from bot.utils.time_utils import get_extension_message

            message = get_extension_message(old_end_time, new_end_time)

            for bid in participants:
                bidder = db.query(User).filter(User.id == bid.bidder_id).first()
                if bidder:
                    await self.send_notification(bidder.telegram_id, message)

            # Уведомляем продавца
            seller = db.query(User).filter(User.id == lot.seller_id).first()
            if seller:
                seller_message = f"""
⏰ <b>Аукцион продлен!</b>

🏷️ {lot.title}
🔄 Из-за ставки в последнюю минуту аукцион автоматически продлен на 10 минут.

📅 Новое время окончания: {new_end_time.strftime('%H:%M')} (было {old_end_time.strftime('%H:%M')})

💰 Текущая цена: {lot.current_price:,.2f} ₽
                """
                await self.send_notification(seller.telegram_id, seller_message.strip())

        except Exception as e:
            logger.error(f"Ошибка при уведомлении о продлении аукциона: {e}")
        finally:
            db.close()

    async def notify_outbid(
        self, lot_id: int, outbid_user_id: int, new_price: float
    ) -> None:
        """Уведомляет пользователя, что его перебили"""
        db = SessionLocal()
        try:
            lot = db.query(Lot).filter(Lot.id == lot_id).first()
            if not lot:
                return
            user = db.query(User).filter(User.id == outbid_user_id).first()
            if not user:
                return
            message = f"""
⚠️ <b>Ваша ставка перебита</b>

🏷️ {lot.title}
💰 Новая текущая цена: {new_price:,.2f} ₽
➡️ Попробуйте повысить ставку, чтобы вернуть лидерство
            """
            await self.send_notification(
                user.telegram_id,
                message.strip(),
                topic=f"lot:{lot_id}:outbid",
                silent=True,
            )
        except Exception as e:
            logger.error(f"Ошибка при уведомлении о перебитой ставке: {e}")
        finally:
            db.close()

    async def notify_autobid_rejected(
        self, lot_id: int, user_id: int, reason: str
    ) -> None:
        """Уведомляет пользователя об отклонении его автоставки"""
        db = SessionLocal()
        try:
            lot = db.query(Lot).filter(Lot.id == lot_id).first()
            if not lot:
                return
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return
            message = f"""
🚫 <b>Автоставка отклонена</b>

🏷️ {lot.title}
❌ Причина: {reason}
💰 Текущая цена лота: {lot.current_price:,.2f} ₽
            """
            await self.send_notification(user.telegram_id, message.strip())
        except Exception as e:
            logger.error(f"Ошибка при уведомлении об отклонении автоставки: {e}")
        finally:
            db.close()

    async def notify_purchase_started(self, lot_id: int, buyer_id: int) -> None:
        """Уведомляет продавца, что покупатель начал оплату"""
        db = SessionLocal()
        try:
            lot = db.query(Lot).filter(Lot.id == lot_id).first()
            buyer = db.query(User).filter(User.id == buyer_id).first()
            seller = (
                db.query(User).filter(User.id == lot.seller_id).first() if lot else None
            )
            if lot and buyer and seller:
                message = f"""
💳 <b>Покупатель приступил к оплате</b>

🏷️ {lot.title}
👤 Покупатель: {buyer.first_name or buyer.username or buyer.id}
💰 Сумма: {lot.current_price:,.2f} ₽
                """
                await self.send_notification(seller.telegram_id, message.strip())
        except Exception as e:
            logger.error(f"Ошибка при уведомлении о начале оплаты: {e}")
        finally:
            db.close()

    async def notify_purchase_completed(
        self, lot_id: int, buyer_id: int, amount: float
    ) -> None:
        """Уведомляет продавца и покупателя об успешной оплате"""
        db = SessionLocal()
        try:
            lot = db.query(Lot).filter(Lot.id == lot_id).first()
            buyer = db.query(User).filter(User.id == buyer_id).first()
            seller = (
                db.query(User).filter(User.id == lot.seller_id).first() if lot else None
            )
            if lot and buyer and seller:
                msg_buyer = f"""
✅ <b>Оплата получена</b>

🏷️ {lot.title}
💰 Сумма: {amount:,.2f} ₽
📞 Свяжитесь с продавцом для завершения сделки
                """
                msg_seller = f"""
✅ <b>Покупка оплачена</b>

🏷️ {lot.title}
💰 Сумма: {amount:,.2f} ₽
👤 Покупатель: {buyer.first_name or buyer.username or buyer.id}
                """
                await self.send_notification(buyer.telegram_id, msg_buyer.strip())
                await self.send_notification(seller.telegram_id, msg_seller.strip())
        except Exception as e:
            logger.error(f"Ошибка при уведомлении об успешной оплате: {e}")
        finally:
            db.close()

    async def _schedule_single_reminder(
        self, lot_id: int, when: datetime, label: str
    ) -> None:
        """Ожидает до времени when и отправляет напоминание участникам, если ещё не отправлено"""
        key = (lot_id, label)
        if key in self._scheduled_reminders:
            return
        self._scheduled_reminders.add(key)
        now = get_moscow_time()
        delay = (when - now).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)
        # При срабатывании проверяем, что аукцион всё ещё активен
        db = SessionLocal()
        try:
            lot = db.query(Lot).filter(Lot.id == lot_id).first()
            if not lot or lot.status != LotStatus.ACTIVE or not lot.end_time:
                return
            # Определяем количество часов до конца, чтобы составить текст
            time_left = (
                lot.end_time - get_moscow_time().replace(tzinfo=None)
            ).total_seconds()
            hours_left = max(int(time_left // 3600), 0)
            await self.notify_auction_ending(lot_id, hours_left)
        finally:
            db.close()

    async def schedule_reminders_for_lot(self, lot: Lot) -> None:
        """Планирует напоминания за 3ч, 2ч, 1ч и 10мин до конца торгов"""
        if not lot.end_time:
            return
        end_naive = lot.end_time
        # Временные отметки
        marks = [
            ("3h", timedelta(hours=3)),
            ("2h", timedelta(hours=2)),
            ("1h", timedelta(hours=1)),
            ("10m", timedelta(minutes=10)),
        ]
        for label, delta in marks:
            when = end_naive - delta
            # Планируем только если время ещё не прошло
            if when > get_moscow_time().replace(tzinfo=None):
                asyncio.create_task(self._schedule_single_reminder(lot.id, when, label))

    async def check_ended_auctions(self) -> None:
        """Проверяет завершенные аукционы и определяет победителей"""
        db = SessionLocal()
        try:
            now = get_moscow_time()
            logger.info(f"Проверка завершенных аукционов. Текущее время: {now}")

            ended_lots = (
                db.query(Lot)
                .filter(
                    Lot.status == LotStatus.ACTIVE,
                    Lot.end_time <= now.replace(tzinfo=None),
                )
                .all()
            )

            logger.info(f"Найдено завершенных лотов: {len(ended_lots)}")

            for lot in ended_lots:
                # Проверяем, не обрабатывали ли мы уже этот лот
                if lot.id in self.processed_lots:
                    logger.info(f"Лот #{lot.id} уже обработан, пропускаем")
                    continue

                logger.info(f"Обработка завершенного лота #{lot.id}: {lot.title}")
                logger.info(f"Время окончания: {lot.end_time}, Текущее время: {now}")

                # Находим победителя (максимальная ставка)
                winning_bid = (
                    db.query(Bid)
                    .filter(Bid.lot_id == lot.id)
                    .order_by(Bid.amount.desc())
                    .first()
                )

                if winning_bid:
                    logger.info(
                        f"Победитель лота #{lot.id}: пользователь {winning_bid.bidder_id}, сумма: {winning_bid.amount}"
                    )

                    # Обновляем статус лота
                    lot.status = LotStatus.SOLD
                    db.commit()
                    logger.info(f"Лот #{lot.id} помечен как проданный")

                    # Добавляем лот в обработанные
                    self.processed_lots.add(lot.id)

                    # Уведомляем победителя
                    await self.notify_auction_winner(
                        lot.id, winning_bid.bidder_id, winning_bid.amount
                    )

                    # Уведомляем продавца
                    seller = db.query(User).filter(User.id == lot.seller_id).first()
                    if seller:
                        message = f"""
💰 <b>Аукцион завершен!</b>

🏷️ {lot.title}
💰 Финальная цена: {winning_bid.amount:,.2f} ₽
👤 Победитель: {db.query(User).filter(User.id == winning_bid.bidder_id).first().first_name}

💳 Ожидайте оплаты от покупателя
                        """
                        await self.send_notification(
                            seller.telegram_id, message.strip()
                        )
                else:
                    logger.info(f"На лоте #{lot.id} нет ставок")
                    # Добавляем лот в обработанные даже если нет ставок
                    self.processed_lots.add(lot.id)

        except Exception as e:
            logger.error(f"Ошибка при проверке завершенных аукционов: {e}")
        finally:
            db.close()

    async def check_lot_end(self, lot_id: int):
        """Проверяет и завершает лот по id, отправляет уведомление победителю или редактирует сообщение в канале если ставок не было"""
        db = SessionLocal()
        try:
            lot = db.query(Lot).filter(Lot.id == lot_id).first()
            now = get_moscow_time().replace(tzinfo=None)
            if not lot or lot.status != LotStatus.ACTIVE:
                return
            if lot.end_time is None or lot.end_time > now:
                return
            # Находим победителя (максимальная ставка)
            winning_bid = (
                db.query(Bid)
                .filter(Bid.lot_id == lot.id)
                .order_by(Bid.amount.desc())
                .first()
            )
            if winning_bid:
                lot.status = LotStatus.SOLD
                db.commit()
                await self.notify_auction_winner(
                    lot.id, winning_bid.bidder_id, winning_bid.amount
                )
                seller = db.query(User).filter(User.id == lot.seller_id).first()
                if seller:
                    message = f"""
💰 <b>Аукцион завершен!</b>
\n🏷️ {lot.title}
💰 Финальная цена: {winning_bid.amount:,.2f} ₽
👤 Победитель: {db.query(User).filter(User.id == winning_bid.bidder_id).first().first_name}
\n💳 Ожидайте оплаты от покупателя
                    """
                    await self.send_notification(seller.telegram_id, message.strip())
            else:
                # Нет ставок — переводим в SOLD и редактируем сообщение в канале
                lot.status = LotStatus.SOLD
                db.commit()
                if lot.telegram_message_id:
                    text = (
                        f"🏷️ <b>{lot.title}</b>\n\n❌ Аукцион завершён. Победителей нет."
                    )
                    await telegram_publisher.edit_lot_message(
                        lot.id, lot.telegram_message_id, text
                    )
        except Exception as e:
            logger.error(f"Ошибка при индивидуальной проверке завершения лота: {e}")
        finally:
            db.close()

    async def schedule_lot_end_check(self, lot_id: int, end_time):
        """Планирует проверку окончания лота на момент end_time"""
        now = get_moscow_time().replace(tzinfo=None)
        delay = (end_time - now).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)
        await self.check_lot_end(lot_id)

    async def schedule_all_active_lots(self):
        """Планирует задачи для всех активных лотов при запуске"""
        db = SessionLocal()
        try:
            now = get_moscow_time().replace(tzinfo=None)
            active_lots = (
                db.query(Lot)
                .filter(
                    Lot.status == LotStatus.ACTIVE,
                    Lot.end_time != None,
                    Lot.end_time > now,
                )
                .all()
            )
            for lot in active_lots:
                asyncio.create_task(self.schedule_lot_end_check(lot.id, lot.end_time))
        except Exception as e:
            logger.error(f"Ошибка при планировании задач для активных лотов: {e}")
        finally:
            db.close()

    async def run_notification_service(self) -> None:
        """Запускает сервис уведомлений"""
        logger.info("Сервис уведомлений запущен")
        await self.schedule_all_active_lots()
        while True:
            try:
                logger.info("Выполняется проверка аукционов...")

                # Проверяем заканчивающиеся аукционы
                await self.check_ending_auctions()

                # Проверяем завершенные аукционы
                await self.check_ended_auctions()

                logger.info(
                    f"Проверка завершена. Ожидание {self.notification_interval} минут..."
                )

                # Пере-планируем напоминания для появившихся новых активных лотов
                await self.schedule_all_active_lots()

                # Ждем следующей проверки
                await asyncio.sleep(self.notification_interval * 60)

            except Exception as e:
                logger.error(f"Ошибка в сервисе уведомлений: {e}")
                await asyncio.sleep(60)  # Ждем минуту при ошибке

    async def close(self) -> None:
        """Закрывает соединение с ботом"""
        await self.bot.session.close()


# Глобальный экземпляр сервиса уведомлений
notification_service = NotificationService()


async def start_notification_service():
    """Запускает сервис уведомлений"""
    await notification_service.run_notification_service()


async def notify_answered_support_questions(bot):
    """Периодически отправляет ответы на вопросы поддержки пользователям."""
    from sqlalchemy.orm import Session

    from database.db import SessionLocal

    while True:
        db: Session = SessionLocal()
        try:
            questions = (
                db.query(SupportQuestion)
                .filter(
                    SupportQuestion.status == "answered",
                    SupportQuestion.notified == False,
                )
                .all()
            )
            for q in questions:
                user = db.query(User).filter(User.id == q.user_id).first()
                if user and user.telegram_id:
                    text = (
                        f"📞 <b>Ответ на ваш вопрос #{q.id}</b>\n\n{q.answer}\n\n"
                        f"💬 Для нового вопроса используйте /support"
                    )
                    try:
                        await notification_service.send_notification(
                            user.telegram_id, text
                        )
                        q.notified = True
                        db.commit()
                    except Exception as e:
                        import logging

                        logging.getLogger(__name__).error(
                            f"Ошибка отправки ответа поддержки: {e}"
                        )
        finally:
            db.close()
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(start_notification_service())
