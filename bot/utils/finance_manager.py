import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from config.settings import (
    AUTO_BID_MIN_BALANCE,
    AUTO_BID_MIN_PAYMENTS,
    COMMISSION_PERCENT,
    PENALTY_PERCENT,
)
from database.db import SessionLocal
from database.models import Bid, Lot, Payment, User, UserRole

logger = logging.getLogger(__name__)


class FinanceManager:
    """Менеджер финансовой системы аукциона"""

    def __init__(self):
        self.commission_percent = COMMISSION_PERCENT
        self.penalty_percent = PENALTY_PERCENT
        self.auto_bid_min_balance = AUTO_BID_MIN_BALANCE
        self.auto_bid_min_payments = AUTO_BID_MIN_PAYMENTS

    def calculate_commission(self, final_price: float) -> float:
        """Рассчитывает комиссию (5% от финальной стоимости)"""
        return final_price * (self.commission_percent / 100)

    def calculate_penalty(self, current_price: float) -> float:
        """Рассчитывает штраф за удаление лота (5% от текущей стоимости)"""
        return current_price * (self.penalty_percent / 100)

    def check_auto_bid_eligibility(self, user: User) -> Tuple[bool, str]:
        """Проверяет право пользователя на автоставки"""
        if user.auto_bid_enabled:
            return True, "Автоставки уже включены"

        if (
            user.successful_payments >= self.auto_bid_min_payments
            or user.balance >= self.auto_bid_min_balance
        ):
            return True, (
                f"Баланс ≥ {self.auto_bid_min_balance}"
                if user.balance >= self.auto_bid_min_balance
                else f"Успешных покупок ≥ {self.auto_bid_min_payments}"
            )

        return (
            False,
            f"Требуется: {self.auto_bid_min_payments}+ успешных покупок",
        )

    def enable_auto_bid(self, user_id: int) -> bool:
        """Включает автоставки для пользователя"""
        db = SessionLocal()

        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return False

            eligible, reason = self.check_auto_bid_eligibility(user)
            if not eligible:
                logger.warning(
                    f"Пользователь {user_id} не имеет права на автоставки: {reason}"
                )
                return False

            user.auto_bid_enabled = True
            db.commit()

            logger.info(f"Автоставки включены для пользователя {user_id}")
            return True

        except Exception as e:
            logger.error(
                f"Ошибка при включении автоставок для пользователя {user_id}: {e}"
            )
            return False
        finally:
            db.close()

    def disable_auto_bid(self, user_id: int) -> bool:
        """Отключает автоставки для пользователя"""
        db = SessionLocal()

        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return False

            user.auto_bid_enabled = False
            db.commit()

            logger.info(f"Автоставки отключены для пользователя {user_id}")
            return True

        except Exception as e:
            logger.error(
                f"Ошибка при отключении автоставок для пользователя {user_id}: {e}"
            )
            return False
        finally:
            db.close()

    def add_balance(
        self, user_id: int, amount: float, reason: str = "Пополнение"
    ) -> bool:
        """Пополняет баланс пользователя (универсально)"""
        db = SessionLocal()

        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return False

            user.balance += amount

            # Создаем запись о платеже
            payment = Payment(
                user_id=user_id,
                amount=amount,
                payment_type="deposit",
                status="completed",
                transaction_id=f"DEP_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            )
            db.add(payment)
            db.commit()

            logger.info(f"Баланс пользователя {user_id} пополнен на {amount}₽")
            return True

        except Exception as e:
            logger.error(f"Ошибка при пополнении баланса пользователя {user_id}: {e}")
            return False
        finally:
            db.close()

    def deduct_balance(
        self, user_id: int, amount: float, reason: str = "Списание"
    ) -> bool:
        """Списывает средства с баланса пользователя (универсально)"""
        db = SessionLocal()

        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return False

            if user.balance < amount:
                logger.warning(
                    f"Недостаточно средств у пользователя {user_id}: {user.balance}₽ < {amount}₽"
                )
                return False

            user.balance -= amount

            # Создаем запись о платеже
            payment = Payment(
                user_id=user_id,
                amount=-amount,
                payment_type="deduction",
                status="completed",
                transaction_id=f"DED_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            )
            db.add(payment)
            db.commit()

            logger.info(f"С баланса пользователя {user_id} списано {amount}₽")
            return True

        except Exception as e:
            logger.error(f"Ошибка при списании средств у пользователя {user_id}: {e}")
            return False
        finally:
            db.close()

    def process_lot_sale(self, lot_id: int, buyer_id: int, final_price: float) -> bool:
        """Обрабатывает продажу лота из баланса покупателя с комиссией 5% площадке и зачислением 95% продавцу"""
        db = SessionLocal()

        try:
            lot = db.query(Lot).filter(Lot.id == lot_id).first()
            buyer = db.query(User).filter(User.id == buyer_id).first()
            seller = (
                db.query(User).filter(User.id == lot.seller_id).first() if lot else None
            )

            if not lot or not buyer or not seller:
                return False

            # Рассчитываем комиссию
            commission = self.calculate_commission(final_price)
            seller_income = final_price - commission

            # Проверяем баланс покупателя
            if buyer.balance < final_price:
                logger.warning(
                    f"Недостаточно средств у покупателя {buyer_id}: {buyer.balance}₽ < {final_price}₽"
                )
                return False

            # Списываем с покупателя
            buyer.balance -= final_price

            # Создаем запись о платеже
            direct_payment = Payment(
                user_id=buyer_id,
                lot_id=lot_id,
                amount=final_price,
                payment_type="purchase",
                status="completed",
                transaction_id=f"DIR_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            )
            db.add(direct_payment)

            # Зачисляем продавцу 95%
            seller.balance += seller_income
            seller_income_payment = Payment(
                user_id=seller.id,
                lot_id=lot_id,
                amount=seller_income,
                payment_type="payout",
                status="completed",
                transaction_id=f"SELL_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            )
            db.add(seller_income_payment)

            # Комиссия площадке 5% — зачисляем супер-админу (или сумме супер-админов)
            super_admins = (
                db.query(User).filter(User.role == UserRole.SUPER_ADMIN).all()
            )
            if super_admins:
                per_admin = commission / len(super_admins)
                for sa in super_admins:
                    sa.balance += per_admin
                    db.add(
                        Payment(
                            user_id=sa.id,
                            lot_id=lot_id,
                            amount=per_admin,
                            payment_type="commission",
                            status="completed",
                            transaction_id=f"COM_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                        )
                    )

            # Увеличиваем счетчик успешных покупок у покупателя
            buyer.successful_payments += 1

            # Обновляем статус лота
            lot.status = LotStatus.SOLD
            lot.current_price = final_price

            db.commit()

            logger.info(
                f"Лот {lot_id} продан за {final_price}₽ (прямая оплата), комиссия: {commission}₽"
            )
            return True

        except Exception as e:
            logger.error(f"Ошибка при обработке продажи лота {lot_id}: {e}")
            return False
        finally:
            db.close()

    def process_lot_deletion(self, lot_id: int, seller_id: int) -> bool:
        """Обрабатывает удаление активного лота: списывает 5% штраф с продавца и зачисляет его на баланс площадки"""
        db = SessionLocal()

        try:
            lot = db.query(Lot).filter(Lot.id == lot_id).first()
            seller = db.query(User).filter(User.id == seller_id).first()

            if not lot or not seller:
                return False

            # Рассчитываем штраф
            penalty = self.calculate_penalty(lot.current_price)

            # Проверяем баланс продавца
            if seller.balance < penalty:
                logger.warning(
                    f"Недостаточно средств у продавца {seller_id} для штрафа {penalty}₽"
                )
                return False

            # Списываем штраф с продавца
            seller.balance -= penalty
            db.add(
                Payment(
                    user_id=seller_id,
                    lot_id=lot_id,
                    amount=-penalty,
                    payment_type="penalty",
                    status="completed",
                    transaction_id=f"PEN_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                )
            )

            # Зачисляем штраф площадке (супер-админам)
            super_admins = (
                db.query(User).filter(User.role == UserRole.SUPER_ADMIN).all()
            )
            if super_admins:
                per_admin = penalty / len(super_admins)
                for sa in super_admins:
                    sa.balance += per_admin
                    db.add(
                        Payment(
                            user_id=sa.id,
                            lot_id=lot_id,
                            amount=per_admin,
                            payment_type="penalty_income",
                            status="completed",
                            transaction_id=f"PENI_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                        )
                    )
            db.commit()

            logger.info(f"Штраф за удаление лота {lot_id}: {penalty}₽")
            return True

        except Exception as e:
            logger.error(f"Ошибка при обработке удаления лота {lot_id}: {e}")
            return False
        finally:
            db.close()

    def get_user_financial_summary(self, user_id: int) -> dict:
        """Получает финансовую сводку пользователя"""
        db = SessionLocal()

        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return {}

            # Статистика платежей
            payments = db.query(Payment).filter(Payment.user_id == user_id).all()

            total_deposits = sum(
                p.amount for p in payments if p.payment_type == "deposit"
            )
            total_deductions = sum(
                abs(p.amount) for p in payments if p.payment_type == "deduction"
            )
            total_commissions = sum(
                p.amount for p in payments if p.payment_type == "commission"
            )
            total_penalties = sum(
                p.amount for p in payments if p.payment_type == "penalty"
            )

            return {
                "balance": (
                    user.balance
                    if user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]
                    else 0
                ),
                "successful_payments": user.successful_payments,
                "auto_bid_enabled": user.auto_bid_enabled,
                "total_deposits": total_deposits,
                "total_deductions": total_deductions,
                "total_commissions": total_commissions,
                "total_penalties": total_penalties,
                "strikes": user.strikes,
            }

        except Exception as e:
            logger.error(
                f"Ошибка при получении финансовой сводки пользователя {user_id}: {e}"
            )
            return {}
        finally:
            db.close()


# Создаем глобальный экземпляр
finance_manager = FinanceManager()
