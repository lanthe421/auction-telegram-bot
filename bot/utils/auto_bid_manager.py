import logging
from datetime import datetime
from typing import Optional

from bot.utils.bid_calculator import calculate_min_bid
from bot.utils.notifications import notification_service
from bot.utils.time_utils import extend_auction_end_time, should_extend_auction
from database.db import SessionLocal
from database.models import Bid, Lot, LotStatus, User

logger = logging.getLogger(__name__)


class AutoBidManager:
    """Менеджер автоматических ставок"""

    @staticmethod
    def process_new_bid(lot_id: int, new_bid_amount: float, new_bidder_id: int) -> None:
        """
        Обрабатывает новую ставку и автоматически повышает ставки других участников

        Args:
            lot_id: ID лота
            new_bid_amount: Сумма новой ставки
            new_bidder_id: ID участника, сделавшего ставку
        """
        db = SessionLocal()
        try:
            # Получаем лот
            lot = db.query(Lot).filter(Lot.id == lot_id).first()
            if not lot or lot.status != LotStatus.ACTIVE:
                return

            # Получаем всех участников с автоставками
            # Исключаем тех, у кого max_bid_amount = None (отключенные автоставки)
            auto_bid_users = (
                db.query(User)
                .filter(
                    User.auto_bid_enabled == True,
                    User.max_bid_amount.isnot(None),  # Только активные автоставки
                    User.id != new_bidder_id,  # Исключаем того, кто сделал ставку
                )
                .all()
            )

            # Проксирование автоставок: выбираем лидера и целевую цену по правилам
            if not auto_bid_users:
                return

            # Текущая цена и шаг
            current_price = lot.current_price
            min_bid_now = calculate_min_bid(current_price)
            increment = min_bid_now - current_price

            # Собираем информацию по автоставкам: (user, max_amount, last_bid_time)
            bidders_info = []
            for u in auto_bid_users:
                # Пропускаем продавца на свой лот (дополнительная защита)
                if u.id == lot.seller_id:
                    continue
                last_bid = (
                    db.query(Bid)
                    .filter(Bid.lot_id == lot.id, Bid.bidder_id == u.id)
                    .order_by(Bid.created_at.desc())
                    .first()
                )
                # Требуем, чтобы пользователь уже участвовал в этом лоте (не авто-присоединяем новых)
                if not last_bid:
                    continue
                last_time = last_bid.created_at
                bidders_info.append((u, float(u.max_bid_amount), last_time))

            if not bidders_info:
                return

            # Находим максимальные лимиты
            highest_max = max(m for _, m, _ in bidders_info)
            if highest_max <= current_price:
                return
            highest_candidates = [
                (u, m, t) for (u, m, t) in bidders_info if m == highest_max
            ]

            # Определяем второй максимум среди остальных и текущую цену
            others_max = [m for (_, m, _) in bidders_info if m != highest_max]
            second_max = (
                max([current_price] + others_max)
                if others_max
                else max(current_price, 0)
            )

            # Лидер среди кандидатов по правилу: кто раньше (по последней ставке), затем по ID
            highest_candidates.sort(key=lambda x: (x[2], x[0].id))
            winner_user = highest_candidates[0][0]

            # Целевая цена: не вся максимальная, а second_max + шаг, но не меньше current_price + шаг и не больше highest_max
            target_price = max(current_price + increment, second_max + increment)
            target_price = min(target_price, highest_max)

            if target_price <= current_price:
                return

            # Определяем предыдущего лидера для уведомления
            previous_top_bid = (
                db.query(Bid)
                .filter(Bid.lot_id == lot.id)
                .order_by(Bid.amount.desc())
                .first()
            )

            # Проверяем, нужно ли продлить аукцион
            auction_extended = False
            old_end_time = lot.end_time
            if lot.end_time and should_extend_auction(lot.end_time):
                # Продлеваем аукцион на 10 минут
                lot.end_time = extend_auction_end_time(lot.end_time)
                auction_extended = True
                logger.info(
                    f"Аукцион {lot.id} автоматически продлен до {lot.end_time} (автоставка)"
                )

            # Фиксируем автоставку лидера
            new_bid = Bid(
                lot_id=lot.id,
                bidder_id=winner_user.id,
                amount=target_price,
                is_auto_bid=True,
            )
            db.add(new_bid)
            lot.current_price = target_price
            db.commit()

            logger.info(
                f"Автоставка лидера user_id={winner_user.id} установлена {target_price} (лимит: {highest_max}, second_max: {second_max}, шаг: {increment})"
            )

            # Уведомляем о продлении аукциона, если произошло
            if auction_extended:
                try:
                    import asyncio

                    asyncio.create_task(
                        notification_service.notify_auction_extended(
                            lot.id, old_end_time, lot.end_time
                        )
                    )
                except Exception as e:
                    logger.error(
                        f"Ошибка при уведомлении о продлении аукциона (авто): {e}"
                    )

            # Уведомляем предыдущего лидера, если изменился
            try:
                if previous_top_bid and previous_top_bid.bidder_id != winner_user.id:
                    import asyncio

                    asyncio.create_task(
                        notification_service.notify_outbid(
                            lot.id, previous_top_bid.bidder_id, target_price
                        )
                    )
            except Exception as e:
                logger.error(f"Ошибка при уведомлении о перебитой ставке (авто): {e}")

        except Exception as e:
            logger.error(f"Ошибка при обработке автоставок для лота {lot_id}: {e}")
        finally:
            db.close()

    @staticmethod
    def _process_user_auto_bid(
        db: SessionLocal,
        lot: Lot,
        user: User,
        new_bid_amount: float,
        new_bidder_id: int,
    ) -> None:
        """
        Обрабатывает автоставку для конкретного пользователя

        Args:
            db: Сессия базы данных
            lot: Лот
            user: Пользователь с автоставкой
            new_bid_amount: Сумма новой ставки
            new_bidder_id: ID участника, сделавшего ставку
        """
        try:
            # Запретить автоставку для продавца на свой лот
            if user.id == lot.seller_id:
                logger.warning(
                    f"Попытка продавца (user_id={user.id}, tg_id={user.telegram_id}) использовать автоставку на свой лот (lot_id={lot.id}) через AutoBidManager"
                )
                return

            # Получаем последнюю ставку пользователя на этот лот
            last_user_bid = (
                db.query(Bid)
                .filter(Bid.lot_id == lot.id, Bid.bidder_id == user.id)
                .order_by(Bid.created_at.desc())
                .first()
            )

            # Определяем минимальную ставку для участия (от текущей цены лота)
            min_required_bid = calculate_min_bid(lot.current_price)

            # Если пользователь еще не делал ставки на этот лот
            if not last_user_bid:
                # Проверяем, стоит ли входить в торги (новая ставка + шаг должны быть меньше лимита)
                if min_required_bid >= user.max_bid_amount:
                    return  # Лимит автоставки слишком мал для участия
                # Участвуем в торгах
            else:
                # Пользователь уже участвовал, проверяем нужно ли повышать
                if lot.current_price <= last_user_bid.amount:
                    return  # Текущая цена не выше нашей последней ставки

            # Определяем текущего лидера до повышения автоставки (для уведомления о перебитии)
            previous_top_bid = (
                db.query(Bid)
                .filter(Bid.lot_id == lot.id)
                .order_by(Bid.amount.desc())
                .first()
            )

            # Проверяем, нужно ли продлить аукцион
            auction_extended = False
            old_end_time = lot.end_time
            if lot.end_time and should_extend_auction(lot.end_time):
                # Продлеваем аукцион на 10 минут
                lot.end_time = extend_auction_end_time(lot.end_time)
                auction_extended = True
                logger.info(
                    f"Аукцион {lot.id} автоматически продлен до {lot.end_time} (индивидуальная автоставка)"
                )

            # Используем уже рассчитанную минимальную ставку
            final_bid_amount = min_required_bid

            # Проверяем, не превышает ли новая ставка максимальную сумму пользователя
            if final_bid_amount > user.max_bid_amount:
                logger.info(
                    f"Автоставка пользователя {user.id} достигла максимума {user.max_bid_amount}"
                )
                return

            # Создаем новую автоставку
            new_bid = Bid(
                lot_id=lot.id,
                bidder_id=user.id,
                amount=final_bid_amount,
                is_auto_bid=True,
            )
            db.add(new_bid)

            # Обновляем цену лота
            lot.current_price = final_bid_amount

            # Сохраняем изменения сразу
            db.commit()

            logger.info(
                f"Автоставка пользователя {user.id} повышена до {final_bid_amount} (максимум: {user.max_bid_amount})"
            )

            # Уведомляем о продлении аукциона, если произошло
            if auction_extended:
                try:
                    import asyncio

                    asyncio.create_task(
                        notification_service.notify_auction_extended(
                            lot.id, old_end_time, lot.end_time
                        )
                    )
                except Exception as e:
                    logger.error(
                        f"Ошибка при уведомлении о продлении аукциона (индивидуальная авто): {e}"
                    )

            # Уведомляем предыдущего лидера, если это был другой пользователь
            try:
                if previous_top_bid and previous_top_bid.bidder_id != user.id:
                    # Отправляем уведомление о перебитой ставке
                    import asyncio

                    asyncio.create_task(
                        notification_service.notify_outbid(
                            lot.id, previous_top_bid.bidder_id, final_bid_amount
                        )
                    )
            except Exception as e:
                logger.error(f"Ошибка при уведомлении о перебитой ставке (авто): {e}")

        except Exception as e:
            logger.error(f"Ошибка при обработке автоставки пользователя {user.id}: {e}")

    @staticmethod
    def get_user_auto_bid_info(user_id: int, lot_id: int) -> Optional[dict]:
        """
        Получает информацию об автоставке пользователя на конкретный лот

        Args:
            user_id: ID пользователя
            lot_id: ID лота

        Returns:
            dict: Информация об автоставке или None
        """
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user or not user.auto_bid_enabled or not user.max_bid_amount:
                return None

            # Получаем последнюю ставку пользователя на этот лот
            last_bid = (
                db.query(Bid)
                .filter(Bid.lot_id == lot_id, Bid.bidder_id == user_id)
                .order_by(Bid.created_at.desc())
                .first()
            )

            if not last_bid:
                return None

            return {
                "current_bid": last_bid.amount,
                "max_amount": user.max_bid_amount,
                "can_increase": last_bid.amount < user.max_bid_amount,
            }

        except Exception as e:
            logger.error(f"Ошибка при получении информации об автоставке: {e}")
            return None
        finally:
            db.close()

    @staticmethod
    def disable_auto_bid_for_lot(user_id: int, lot_id: int) -> bool:
        """
        Отключает автоставку пользователя для конкретного лота

        Args:
            user_id: ID пользователя
            lot_id: ID лота

        Returns:
            bool: True если успешно отключено
        """
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return False

            # Сбрасываем максимальную сумму автоставки
            user.max_bid_amount = None
            db.commit()

            logger.info(
                f"Автоставка пользователя {user_id} отключена для лота {lot_id}"
            )
            return True

        except Exception as e:
            logger.error(f"Ошибка при отключении автоставки: {e}")
            return False
        finally:
            db.close()
