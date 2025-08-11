import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.handlers.admin import is_admin
from bot.utils.finance_manager import finance_manager
from bot.utils.keyboards import get_main_keyboard, get_user_profile_keyboard
from database.db import SessionLocal
from database.models import Bid, Lot, LotStatus, User

router = Router()
logger = logging.getLogger(__name__)


async def _ensure_user(message: Message) -> User | None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            user = User(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info("Создан новый пользователь %s", user.telegram_id)
        return user
    except Exception as e:
        logger.error("Ошибка регистрации пользователя: %s", e)
        return None
    finally:
        db.close()


@router.message(Command("profile"))
@router.message(F.text == "👤 Личный кабинет")
async def show_profile(message: Message):
    user = await _ensure_user(message)
    if not user:
        await message.answer("❌ Ошибка. Повторите позже")
        return

    text = (
        f"👤 <b>Личный кабинет</b>\n\n"
        f"Имя: {user.first_name or '—'}\n"
        f"Username: @{user.username or 'N/A'}\n"
        f"Telegram ID: {user.telegram_id}\n"
        f"Баланс: {user.balance:,.2f} ₽\n"
        f"Успешных покупок: {user.successful_payments}\n"
        f"Страйки: {user.strikes}/3\n"
    )

    await message.answer(
        text, reply_markup=get_user_profile_keyboard(), parse_mode="HTML"
    )


@router.message(F.text == "💳 Мой баланс")
async def show_my_balance(message: Message):
    user = await _ensure_user(message)
    if not user:
        await message.answer("❌ Ошибка. Повторите позже")
        return
    await message.answer(
        f"💳 <b>Ваш баланс</b>\n\n" f"Текущий баланс: {user.balance:,.2f} ₽",
        reply_markup=get_user_profile_keyboard(),
        parse_mode="HTML",
    )


@router.message(F.text == "💰 Мои ставки")
async def show_my_bids(message: Message):
    user = await _ensure_user(message)
    if not user:
        await message.answer("❌ Ошибка. Повторите позже")
        return

    db = SessionLocal()
    try:
        bids = (
            db.query(Bid)
            .filter(Bid.bidder_id == user.id)
            .order_by(Bid.created_at.desc())
            .limit(10)
            .all()
        )
        if not bids:
            await message.answer("📋 У вас пока нет ставок")
            return
        text = "📋 <b>Мои последние ставки</b>\n\n"
        for b in bids:
            lot = db.query(Lot).filter(Lot.id == b.lot_id).first()
            if not lot:
                continue
            text += (
                f"🏷️ {lot.title}\n"
                f"💰 Ставка: {b.amount:,.2f} ₽\n"
                f"📅 {b.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            )
        await message.answer(text, parse_mode="HTML")
    finally:
        db.close()


@router.message(F.text == "🎯 Мое участие")
async def show_my_participation(message: Message):
    user = await _ensure_user(message)
    if not user:
        await message.answer("❌ Ошибка. Повторите позже")
        return
    db = SessionLocal()
    try:
        # Активные лоты, где есть ставки пользователя
        active_lot_ids = (
            db.query(Bid.lot_id)
            .distinct()
            .join(Lot, Lot.id == Bid.lot_id)
            .filter(Bid.bidder_id == user.id, Lot.status == LotStatus.ACTIVE)
            .all()
        )
        active_lot_ids = [lid[0] for lid in active_lot_ids]
        if not active_lot_ids:
            await message.answer("🎯 У вас нет активного участия")
            return
        text = "🎯 <b>Мое участие</b>\n\n"
        for lot_id in active_lot_ids[:10]:
            lot = db.query(Lot).filter(Lot.id == lot_id).first()
            if not lot:
                continue
            text += (
                f"🏷️ {lot.title}\n"
                f"💰 Текущая цена: {lot.current_price:,.2f} ₽\n"
                f"⏰ Окончание: {lot.end_time.strftime('%d.%m.%Y %H:%M') if lot.end_time else '—'}\n\n"
            )
        await message.answer(text, parse_mode="HTML")
    finally:
        db.close()


@router.message(F.text == "📋 История торгов")
async def show_trade_history(message: Message):
    user = await _ensure_user(message)
    if not user:
        await message.answer("❌ Ошибка. Повторите позже")
        return
    db = SessionLocal()
    try:
        # Завершенные лоты, где участвовал пользователь
        won_bids = (
            db.query(Bid)
            .join(Lot, Lot.id == Bid.lot_id)
            .filter(Bid.bidder_id == user.id, Lot.status == LotStatus.SOLD)
            .order_by(Bid.created_at.desc())
            .limit(10)
            .all()
        )
        if not won_bids:
            await message.answer("📋 Пока нет завершенных торгов с вашим участием")
            return
        text = "📋 <b>История торгов</b>\n\n"
        for b in won_bids:
            lot = db.query(Lot).filter(Lot.id == b.lot_id).first()
            if not lot:
                continue
            text += (
                f"🏷️ {lot.title}\n"
                f"💰 Ваша ставка: {b.amount:,.2f} ₽\n"
                f"📅 {b.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            )
        await message.answer(text, parse_mode="HTML")
    finally:
        db.close()


@router.message(Command("support"))
@router.message(F.text == "🆘 Поддержка")
async def user_support_entry(message: Message, state: FSMContext):
    # Запускаем сбор вопроса в поддержку
    await message.answer(
        "📝 <b>Обращение в поддержку</b>\n\nОпишите ваш вопрос или проблему.",
        parse_mode="HTML",
    )
    try:
        from bot.handlers.support import SupportStates

        await state.set_state(SupportStates.waiting_for_question)
    except Exception:
        # Если модуль поддержки не подключен
        await message.answer("❌ Служба поддержки недоступна")


@router.callback_query(F.data == "top_up_balance")
async def top_up_info(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "💳 Для пополнения баланса используйте оплату при покупке лота или обратитесь в поддержку."
    )


@router.callback_query(F.data == "start_top_up")
async def start_top_up(callback: CallbackQuery):
    await callback.answer("Функция пополнения будет доступна позже")


@router.callback_query(F.data == "start_withdraw")
async def start_withdraw(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "🔐 Вывод средств производится по запросу в поддержку. Укажите сумму и реквизиты."
    )


@router.callback_query(F.data == "my_participation")
async def my_participation_callback(callback: CallbackQuery):
    await callback.answer()
    # Переиспользуем логику списка участия
    message = Message.model_validate(callback.message.model_dump())
    await show_my_participation(message)


@router.callback_query(F.data == "user_stats")
async def user_stats_callback(callback: CallbackQuery):
    await callback.answer()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not user:
            await callback.message.answer("❌ Пользователь не найден")
            return
        stats = finance_manager.get_user_financial_summary(user.id)
        text = (
            "📊 <b>Статистика аккаунта</b>\n\n"
            f"Успешных покупок: {stats.get('successful_payments', 0)}\n"
            f"Страйки: {stats.get('strikes', 0)}/3\n"
        )
        await callback.message.answer(text, parse_mode="HTML")
    finally:
        db.close()


@router.message(F.text == "⚙️ Настройки")
async def user_settings(message: Message):
    # Если админ — пусть обработает админский хендлер
    if is_admin(message.from_user.id):
        return
    await message.answer(
        "⚙️ <b>Настройки</b>\n\n"
        "Пока доступны базовые функции. Управление расширенными настройками через приложение.",
        parse_mode="HTML",
    )
