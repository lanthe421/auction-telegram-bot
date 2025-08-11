import logging
from datetime import datetime
from typing import Optional

from bot.utils.bid_calculator import calculate_min_bid
from bot.utils.notifications import notification_service
from bot.utils.time_utils import extend_auction_end_time, should_extend_auction
from database.db import SessionLocal
from database.models import AutoBid, Bid, Lot, LotStatus, User

logger = logging.getLogger(__name__)


class AutoBidManager:
    """Менеджер автоматических ставок - новая логика"""

    @staticmethod
    def set_auto_bid(user_id: int, lot_id: int, target_amount: float) -> bool:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            lot = db.query(Lot).filter(Lot.id == lot_id).first()

            if not user or not lot:
                logger.error(f"Пользователь {user_id} или лот {lot_id} не найден")
                return False

            if lot.status != LotStatus.ACTIVE:
                logger.error(f"Лот {lot_id} не активен")
                return False

            if user.id == lot.seller_id:
                logger.error(
                    f"Пользователь {user_id} не может ставить автоставку на свой лот {lot_id}"
                )
                return False

            if target_amount <= lot.current_price:
                logger.error(
                    f"Целевая сумма {target_amount} должна быть больше текущей цены {lot.current_price}"
                )
                return False

            existing_auto_bid = (
                db.query(AutoBid)
                .filter(
                    AutoBid.user_id == user_id,
                    AutoBid.lot_id == lot_id,
                    AutoBid.is_active == True,
                )
                .first()
            )

            if existing_auto_bid:
                existing_auto_bid.target_amount = target_amount
                existing_auto_bid.updated_at = datetime.utcnow()
                logger.info(
                    f"Обновлена автоставка пользователя {user_id} на лот {lot_id}: {target_amount}₽"
                )
            else:
                new_auto_bid = AutoBid(
                    user_id=user_id,
                    lot_id=lot_id,
                    target_amount=target_amount,
                    is_active=True,
                )
                db.add(new_auto_bid)
                logger.info(
                    f"Создана автоставка пользователя {user_id} на лот {lot_id}: {target_amount}₽"
                )

            db.commit()

            # Синхронизация текущей цены с реальным лидером (если отличается)
            current_leader_bid = (
                db.query(Bid)
                .filter(Bid.lot_id == lot.id)
                .order_by(Bid.amount.desc())
                .first()
            )
            if current_leader_bid and current_leader_bid.amount != lot.current_price:
                old_price = lot.current_price
                lot.current_price = current_leader_bid.amount
                db.commit()
                logger.info(
                    f"Синхронизирована цена лота {lot_id} после установки автоставки: {old_price}₽ → {lot.current_price}₽"
                )

            # Запускаем обработку автоставок
            AutoBidManager._process_auto_bids_for_lot(lot_id)
            return True
        except Exception as e:
            logger.error(f"Ошибка при установке автоставки: {e}")
            db.rollback()
            return False
        finally:
            db.close()

    @staticmethod
    def remove_auto_bid(user_id: int, lot_id: int) -> bool:
        db = SessionLocal()
        try:
            auto_bid = (
                db.query(AutoBid)
                .filter(
                    AutoBid.user_id == user_id,
                    AutoBid.lot_id == lot_id,
                    AutoBid.is_active == True,
                )
                .first()
            )

            if auto_bid:
                auto_bid.is_active = False
                db.commit()
                logger.info(
                    f"Удалена автоставка пользователя {user_id} на лот {lot_id}"
                )
                return True
            else:
                logger.warning(
                    f"Автоставка пользователя {user_id} на лот {lot_id} не найдена"
                )
                return False
        except Exception as e:
            logger.error(f"Ошибка при удалении автоставки: {e}")
            db.rollback()
            return False
        finally:
            db.close()

    @staticmethod
    def get_user_auto_bid(user_id: int, lot_id: int) -> Optional[AutoBid]:
        db = SessionLocal()
        try:
            return (
                db.query(AutoBid)
                .filter(
                    AutoBid.user_id == user_id,
                    AutoBid.lot_id == lot_id,
                    AutoBid.is_active == True,
                )
                .first()
            )
        except Exception as e:
            logger.error(f"Ошибка при получении автоставки: {e}")
            return None
        finally:
            db.close()

    @staticmethod
    def process_new_bid(lot_id: int, new_bid_amount: float, new_bidder_id: int) -> None:
        logger.info(
            f"Обработка новой ставки {new_bid_amount}₽ от пользователя {new_bidder_id} на лот {lot_id}"
        )
        # Для совместимости и корректной реакции автоставок после ручной ставки
        # инициируем пересчет, который при необходимости создаст недостающие AutoBid
        AutoBidManager.recalculate_auto_bids_for_lot(lot_id)

    @staticmethod
    def _process_auto_bids_for_lot(lot_id: int) -> None:
        db = SessionLocal()
        try:
            lot = db.query(Lot).filter(Lot.id == lot_id).first()
            if not lot or lot.status != LotStatus.ACTIVE:
                return

            auto_bids = (
                db.query(AutoBid)
                .filter(AutoBid.lot_id == lot_id, AutoBid.is_active == True)
                .all()
            )

            if not auto_bids:
                logger.info(f"Нет активных автоставок на лот {lot_id}")
                return

            old_price = lot.current_price

            # Стабилизационный цикл: повторяем, пока цена меняется
            max_iterations = 20
            for _ in range(max_iterations):
                iteration_changed = False
                for auto_bid in sorted(
                    auto_bids, key=lambda ab: ab.target_amount, reverse=True
                ):
                    if AutoBidManager._process_single_auto_bid(
                        db, lot, auto_bid, lot.current_price
                    ):
                        iteration_changed = True
                if not iteration_changed:
                    break

            new_price = lot.current_price
            if new_price != old_price and AutoBidManager._should_update_channel(
                lot_id, old_price, new_price
            ):
                try:
                    from management.core.telegram_publisher_sync import (
                        TelegramPublisherSync,
                    )

                    TelegramPublisherSync().update_lot_message_with_bid(lot_id)
                    logger.info(
                        f"Обновлено сообщение в канале для лота {lot_id} (цена: {old_price}₽ → {new_price}₽)"
                    )
                except Exception as e:
                    logger.error(f"Ошибка при обновлении сообщения в канале: {e}")
            else:
                logger.info(
                    f"Канал не обновляется для лота {lot_id} (незначительное изменение цены: {old_price}₽ → {new_price}₽)"
                )
        except Exception as e:
            logger.error(f"Ошибка при обработке автоставок для лота {lot_id}: {e}")
        finally:
            db.close()

    # Совместимость со старыми тестами/кодом
    @staticmethod
    def recalculate_auto_bids_for_lot(lot_id: int) -> None:
        """Совместимая обертка. При необходимости создаёт AutoBid из старых полей пользователя и предыдущих авто-ставок."""
        db = SessionLocal()
        try:
            lot = db.query(Lot).filter(Lot.id == lot_id).first()
            if not lot:
                return

            # Если на лоте нет активных AutoBid, но есть пользователи с прежними автофлагами и авто-ставками,
            # создаём записи AutoBid на лету для совместимости.
            has_auto = (
                db.query(AutoBid)
                .filter(AutoBid.lot_id == lot_id, AutoBid.is_active == True)
                .first()
            )
            if not has_auto:
                # Ищем участников с предыдущими авто-ставками
                bidder_ids = [
                    row[0]
                    for row in (
                        db.query(Bid.bidder_id)
                        .filter(Bid.lot_id == lot_id, Bid.is_auto_bid == True)
                        .distinct()
                        .all()
                    )
                ]
                for bidder_id in bidder_ids:
                    user = db.query(User).filter(User.id == bidder_id).first()
                    if not user:
                        continue
                    # Если есть лимит из старой модели — используем его как target_amount
                    target = getattr(user, "max_bid_amount", None)
                    enabled = getattr(user, "auto_bid_enabled", False)
                    if enabled and target and target > lot.current_price:
                        db.add(
                            AutoBid(
                                user_id=bidder_id,
                                lot_id=lot_id,
                                target_amount=float(target),
                                is_active=True,
                            )
                        )
                db.commit()

        except Exception as e:
            logger.error(f"Ошибка совместимости при создании AutoBid: {e}")
            db.rollback()
        finally:
            db.close()

        # После подготовки данных запускаем основную обработку
        AutoBidManager._process_auto_bids_for_lot(lot_id)

    @staticmethod
    def _process_single_auto_bid(
        db: SessionLocal, lot: Lot, auto_bid: AutoBid, current_price: float
    ) -> bool:
        try:
            live_current_price = lot.current_price

            current_leader_bid = (
                db.query(Bid)
                .filter(Bid.lot_id == lot.id)
                .order_by(Bid.amount.desc())
                .first()
            )

            # Если пользователь уже лидер — ничего не делаем
            if current_leader_bid and current_leader_bid.bidder_id == auto_bid.user_id:
                return False

            if auto_bid.target_amount <= live_current_price:
                return False

            # Определяем базовую цену для перебития
            # Если лидер — автоставка другого пользователя, перебиваем её таргет + шаг
            # Иначе (лидер ручной или лидера нет) — текущая цена + шаг
            required_bid: float
            if current_leader_bid and current_leader_bid.bidder_id != auto_bid.user_id:
                if getattr(current_leader_bid, "is_auto_bid", False):
                    # Найдем таргет автоставки текущего лидера
                    leader_auto = (
                        db.query(AutoBid)
                        .filter(
                            AutoBid.user_id == current_leader_bid.bidder_id,
                            AutoBid.lot_id == lot.id,
                            AutoBid.is_active == True,
                        )
                        .first()
                    )
                    if leader_auto and leader_auto.target_amount is not None:
                        required_bid = calculate_min_bid(leader_auto.target_amount)
                    else:
                        required_bid = calculate_min_bid(live_current_price)
                else:
                    required_bid = calculate_min_bid(live_current_price)
            else:
                required_bid = calculate_min_bid(live_current_price)

            if auto_bid.target_amount < required_bid:
                return False
            if live_current_price >= required_bid:
                return False
            new_bid_amount = required_bid

            # Не создаем дубль той же суммы
            existing_bid = (
                db.query(Bid)
                .filter(
                    Bid.lot_id == lot.id,
                    Bid.bidder_id == auto_bid.user_id,
                    Bid.amount == new_bid_amount,
                )
                .first()
            )
            if existing_bid:
                return False

            # Продлеваем аукцион при необходимости
            auction_extended = False
            old_end_time = lot.end_time
            if lot.end_time and should_extend_auction(lot.end_time):
                lot.end_time = extend_auction_end_time(lot.end_time)
                auction_extended = True
                logger.info(f"Аукцион {lot.id} продлен до {lot.end_time}")

            # Создаем ставку
            new_bid = Bid(
                lot_id=lot.id,
                bidder_id=auto_bid.user_id,
                amount=new_bid_amount,
                is_auto_bid=True,
            )
            db.add(new_bid)
            lot.current_price = new_bid_amount
            db.commit()

            logger.info(
                f"Автоставка пользователя {auto_bid.user_id}: {new_bid_amount}₽ (лимит: {auto_bid.target_amount}₽)"
            )

            # Уведомления
            if auction_extended:
                try:
                    import asyncio

                    asyncio.create_task(
                        notification_service.notify_auction_extended(
                            lot.id, old_end_time, lot.end_time
                        )
                    )
                except Exception as e:
                    logger.error(f"Ошибка при уведомлении о продлении аукциона: {e}")

            if current_leader_bid and current_leader_bid.bidder_id != auto_bid.user_id:
                try:
                    import asyncio

                    asyncio.create_task(
                        notification_service.notify_outbid(
                            lot.id, current_leader_bid.bidder_id, new_bid_amount
                        )
                    )
                except Exception as e:
                    logger.error(f"Ошибка при уведомлении о перебитой ставке: {e}")

            return True
        except Exception as e:
            logger.error(f"Ошибка при обработке автоставки {auto_bid.id}: {e}")
            return False

    @staticmethod
    def get_lot_auto_bids(lot_id: int) -> list:
        db = SessionLocal()
        try:
            return (
                db.query(AutoBid)
                .filter(AutoBid.lot_id == lot_id, AutoBid.is_active == True)
                .all()
            )
        except Exception as e:
            logger.error(f"Ошибка при получении автоставок лота {lot_id}: {e}")
            return []
        finally:
            db.close()

    @staticmethod
    def get_user_auto_bids(user_id: int) -> list:
        db = SessionLocal()
        try:
            return (
                db.query(AutoBid)
                .filter(AutoBid.user_id == user_id, AutoBid.is_active == True)
                .all()
            )
        except Exception as e:
            logger.error(f"Ошибка при получении автоставок пользователя {user_id}: {e}")
            return []
        finally:
            db.close()

    @staticmethod
    def cleanup_expired_auto_bids() -> int:
        db = SessionLocal()
        try:
            expired_auto_bids = (
                db.query(AutoBid)
                .join(Lot)
                .filter(
                    AutoBid.is_active == True,
                    Lot.status.in_(
                        [LotStatus.SOLD, LotStatus.CANCELLED, LotStatus.EXPIRED]
                    ),
                )
                .all()
            )

            count = 0
            for auto_bid in expired_auto_bids:
                auto_bid.is_active = False
                count += 1

            if count > 0:
                db.commit()
                logger.info(f"Очищено {count} автоставок на завершенных лотах")

            return count
        except Exception as e:
            logger.error(f"Ошибка при очистке автоставок: {e}")
            db.rollback()
            return 0
        finally:
            db.close()

    @staticmethod
    def _should_update_channel(lot_id: int, old_price: float, new_price: float) -> bool:
        price_change = new_price - old_price
        price_change_percent = (price_change / old_price) * 100 if old_price > 0 else 0
        return price_change_percent >= 10 or price_change >= 1000

    @staticmethod
    def check_auto_bid_with_notifications(
        user_id: int, lot_id: int, target_amount: float
    ) -> dict:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            lot = db.query(Lot).filter(Lot.id == lot_id).first()

            if not user or not lot:
                return {
                    "can_set": False,
                    "message": "Пользователь или лот не найден",
                    "current_leader_amount": 0,
                    "current_leader_name": "",
                }

            if lot.status != LotStatus.ACTIVE:
                return {
                    "can_set": False,
                    "message": "Лот не активен",
                    "current_leader_amount": 0,
                    "current_leader_name": "",
                }

            if user.id == lot.seller_id:
                return {
                    "can_set": False,
                    "message": "Вы не можете ставить автоставку на свой лот",
                    "current_leader_amount": 0,
                    "current_leader_name": "",
                }

            max_auto_bid = (
                db.query(AutoBid)
                .filter(AutoBid.lot_id == lot.id, AutoBid.is_active == True)
                .order_by(AutoBid.target_amount.desc())
                .first()
            )

            current_leader_bid = (
                db.query(Bid)
                .filter(Bid.lot_id == lot.id)
                .order_by(Bid.amount.desc())
                .first()
            )

            current_leader_amount = (
                current_leader_bid.amount if current_leader_bid else lot.current_price
            )
            current_leader_name = "Нет лидера"

            if current_leader_bid:
                leader_user = (
                    db.query(User)
                    .filter(User.id == current_leader_bid.bidder_id)
                    .first()
                )
                current_leader_name = (
                    leader_user.first_name
                    if leader_user
                    else f"User{current_leader_bid.bidder_id}"
                )

            if target_amount <= lot.current_price:
                return {
                    "can_set": False,
                    "message": f"Целевая сумма {target_amount}₽ должна быть больше текущей цены {lot.current_price}₽",
                    "current_leader_amount": current_leader_amount,
                    "current_leader_name": current_leader_name,
                }

            if max_auto_bid and target_amount <= max_auto_bid.target_amount:
                max_auto_bid_user = (
                    db.query(User).filter(User.id == max_auto_bid.user_id).first()
                )
                max_auto_bid_user_name = (
                    max_auto_bid_user.first_name
                    if max_auto_bid_user
                    else f"User{max_auto_bid.user_id}"
                )
                # Минимум для перебития = автоставка прошлого лидера + минимальный шаг
                # calculate_min_bid(base) уже возвращает base + step
                minimal_needed = calculate_min_bid(max_auto_bid.target_amount)
                return {
                    "can_set": False,
                    "message": (
                        f"Ваша автоставка {target_amount}₽ меньше или равна автоставке пользователя "
                        f"{max_auto_bid_user_name} ({max_auto_bid.target_amount}₽). Минимум: {minimal_needed}₽."
                    ),
                    "current_leader_amount": current_leader_amount,
                    "current_leader_name": current_leader_name,
                }

            return {
                "can_set": True,
                "message": f"Автоставка {target_amount}₽ будет установлена. Текущий лидер: {current_leader_name} ({current_leader_amount}₽)",
                "current_leader_amount": current_leader_amount,
                "current_leader_name": current_leader_name,
            }
        except Exception as e:
            logger.error(f"Ошибка при проверке автоставки: {e}")
            return {
                "can_set": False,
                "message": f"Ошибка при проверке автоставки: {e}",
                "current_leader_amount": 0,
                "current_leader_name": "",
            }
        finally:
            db.close()
