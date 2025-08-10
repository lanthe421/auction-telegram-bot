import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.utils.finance_manager import finance_manager
from bot.utils.notifications import notification_service
from database.db import SessionLocal
from database.models import Lot, Payment, User

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("pay_card:"))
async def pay_with_card(callback: CallbackQuery):
    """Оплата картой"""
    db = SessionLocal()
    try:
        lot_id = int(callback.data.split(":")[1])

        # Получаем лот и пользователя
        lot = db.query(Lot).filter(Lot.id == lot_id).first()
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()

        if not lot or not user:
            await callback.answer("❌ Лот или пользователь не найден")
            return

        # Создаем платеж
        payment = Payment(
            user_id=user.id,
            lot_id=lot_id,
            amount=lot.current_price,
            payment_type="card",
            status="pending",
        )
        db.add(payment)
        db.commit()

        await callback.message.answer(
            f"💳 **Оплата картой**\n\n"
            f"🏷️ Лот: {lot.title}\n"
            f"💰 Сумма: {lot.current_price:,.2f} ₽\n"
            f"📊 Статус: Обрабатывается\n\n"
            f"ℹ️ Ссылка на оплату будет отправлена в следующем сообщении"
        )

        await callback.answer("💳 Платеж создан")

        # Уведомляем продавца о начале оплаты
        try:
            await notification_service.notify_purchase_started(lot_id, user.id)
        except Exception as e:
            logger.error(f"Ошибка уведомления о начале оплаты: {e}")

    except Exception as e:
        logger.error(f"Ошибка при создании платежа: {e}")
        await callback.answer("❌ Ошибка при создании платежа")
        db.rollback()
    finally:
        db.close()


@router.callback_query(F.data.startswith("pay_sbp:"))
async def pay_with_sbp(callback: CallbackQuery):
    """Оплата через СБП"""
    db = SessionLocal()
    try:
        lot_id = int(callback.data.split(":")[1])

        # Получаем лот и пользователя
        lot = db.query(Lot).filter(Lot.id == lot_id).first()
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()

        if not lot or not user:
            await callback.answer("❌ Лот или пользователь не найден")
            return

        # Создаем платеж
        payment = Payment(
            user_id=user.id,
            lot_id=lot_id,
            amount=lot.current_price,
            payment_type="sbp",
            status="pending",
        )
        db.add(payment)
        db.commit()

        await callback.message.answer(
            f"📱 **Оплата через СБП**\n\n"
            f"🏷️ Лот: {lot.title}\n"
            f"💰 Сумма: {lot.current_price:,.2f} ₽\n"
            f"📊 Статус: Обрабатывается\n\n"
            f"ℹ️ QR-код для оплаты будет отправлен в следующем сообщении"
        )

        await callback.answer("📱 Платеж создан")

        # Уведомляем продавца о начале оплаты
        try:
            await notification_service.notify_purchase_started(lot_id, user.id)
        except Exception as e:
            logger.error(f"Ошибка уведомления о начале оплаты: {e}")

    except Exception as e:
        logger.error(f"Ошибка при создании платежа: {e}")
        await callback.answer("❌ Ошибка при создании платежа")
        db.rollback()
    finally:
        db.close()


@router.callback_query(F.data.startswith("pay_balance:"))
async def pay_with_balance(callback: CallbackQuery):
    """Оплата с баланса покупателя: списание у покупателя, зачисление продавцу 95%, 5% супер-админам"""
    db = SessionLocal()
    try:
        lot_id = int(callback.data.split(":")[1])

        # Получаем лот и пользователя
        lot = db.query(Lot).filter(Lot.id == lot_id).first()
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        seller = db.query(User).filter(User.id == lot.seller_id).first()

        if not lot or not user or not seller:
            await callback.answer("❌ Лот или пользователь не найден")
            return

        # Списываем с баланса и проводим зачисления
        amount = lot.current_price
        if finance_manager.process_lot_sale(lot.id, user.id, amount):
            await callback.message.answer(
                f"✅ <b>Оплата успешно проведена</b>\n\n"
                f"🏷️ Лот: {lot.title}\n"
                f"💰 Сумма: {amount:,.2f} ₽\n"
                f"📊 Комиссия площадки: {amount*0.05:,.2f} ₽\n"
                f"👤 Продавцу зачислено: {amount*0.95:,.2f} ₽",
                parse_mode="HTML",
            )
            await callback.answer("✅ Оплачено")
            # Уведомления
            try:
                await notification_service.notify_purchase_completed(
                    lot_id, user.id, amount
                )
            except Exception as e:
                logger.error(f"Ошибка уведомления об успешной оплате: {e}")
        else:
            await callback.answer(
                "❌ Недостаточно средств или ошибка оплаты", show_alert=True
            )

    except Exception as e:
        logger.error(f"Ошибка при создании прямого платежа: {e}")
        await callback.answer("❌ Ошибка при создании платежа")
        db.rollback()
    finally:
        db.close()


@router.callback_query(F.data == "cancel_payment")
async def cancel_payment(callback: CallbackQuery):
    """Отмена платежа"""
    await callback.message.edit_text(
        "❌ **Платеж отменен**\n\n" "ℹ️ Вы можете попробовать оплату позже"
    )
    await callback.answer("❌ Платеж отменен")


@router.message(Command("payments"))
async def show_payments(message: Message):
    """Показать историю платежей"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            await message.answer("❌ Пользователь не найден")
            return

        # Получаем последние платежи
        recent_payments = (
            db.query(Payment)
            .filter(Payment.user_id == user.id)
            .order_by(Payment.created_at.desc())
            .limit(10)
            .all()
        )

        if not recent_payments:
            await message.answer("📝 У вас пока нет платежей")
            return

        text = "💳 **История платежей:**\n\n"
        for payment in recent_payments:
            lot = db.query(Lot).filter(Lot.id == payment.lot_id).first()
            status_emoji = (
                "✅"
                if payment.status == "completed"
                else "⏳" if payment.status == "pending" else "❌"
            )

            text += f"{status_emoji} **{payment.payment_type.upper()}**\n"
            if lot:
                text += f"🏷️ Лот: {lot.title}\n"
            text += f"💰 Сумма: {payment.amount:,.2f} ₽\n"
            text += f"📅 Дата: {payment.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"

        await message.answer(text)

    except Exception as e:
        logger.error(f"Ошибка при получении платежей: {e}")
        await message.answer("❌ Ошибка при получении данных")
    finally:
        db.close()
