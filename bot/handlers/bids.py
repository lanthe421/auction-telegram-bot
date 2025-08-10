import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.handlers.bid_states import BidStates
from bot.utils.auto_bid_manager import AutoBidManager
from bot.utils.bid_calculator import calculate_min_bid, validate_bid
from bot.utils.keyboards import get_auction_keyboard
from bot.utils.lot_helpers import get_current_leader
from bot.utils.notifications import notification_service
from bot.utils.time_utils import (
    extend_auction_end_time,
    get_moscow_time,
    should_extend_auction,
)
from config.settings import TELEGRAM_CHANNEL_USERNAME
from database.db import SessionLocal
from database.models import Bid, Lot, LotStatus, User, UserRole
from management.core.telegram_publisher_sync import telegram_publisher_sync

router = Router()
logger = logging.getLogger(__name__)

# Live-обновления убраны для улучшения производительности


async def check_user_banned_callback(callback: CallbackQuery) -> bool:
    """Проверяет, заблокирован ли пользователь (для callback)"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if user and user.is_banned:
            await callback.answer(
                "❌ Ваш аккаунт заблокирован администратором", show_alert=True
            )
            return True
        return False
    except Exception as e:
        logger.error(f"Ошибка при проверке блокировки пользователя: {e}")
        return False
    finally:
        db.close()


@router.callback_query(F.data.startswith("auto_bid:"))
@router.callback_query(F.data.startswith("change_auto_bid:"))
async def handle_auto_bid(callback: CallbackQuery, state: FSMContext):
    """Старт ввода суммы автоставки для конкретного лота."""
    # Блокировки
    if await check_user_banned_callback(callback):
        return

    db = SessionLocal()
    try:
        parts = callback.data.split(":")
        lot_id = int(parts[1])

        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        lot = db.query(Lot).filter(Lot.id == lot_id).first()

        if not user or not lot:
            await callback.answer("❌ Лот или пользователь не найден")
            return

        # Проверяем активность лота
        if lot.status != LotStatus.ACTIVE or (
            lot.end_time is not None
            and lot.end_time <= get_moscow_time().replace(tzinfo=None)
        ):
            await callback.answer("❌ Аукцион завершен")
            return

        # Текущая минимальная ставка по шагу
        min_bid_amount = calculate_min_bid(lot.current_price)

        # Текущий лидер
        leader_info = get_current_leader(db, lot.id)
        leader_text = ""
        if leader_info and leader_info[0]:
            if leader_info[1] is not None:
                leader_text = f"🥇 <b>Текущий лидер:</b> {leader_info[0]} ({leader_info[1]:,.2f} ₽)\n"
            else:
                leader_text = f"🥇 <b>Текущий лидер:</b> {leader_info[0]}\n"

        # Текущая автоставка пользователя, если есть
        existing_auto_bid = AutoBidManager.get_user_auto_bid(user.id, lot.id)
        existing_text = (
            f"\n🤖 <b>Ваша текущая автоставка:</b> {existing_auto_bid.target_amount:,.2f} ₽\n"
            if existing_auto_bid
            else ""
        )

        text = (
            f"🤖 <b>Автоставка</b>\n\n"
            f"🏷️ Лот: {lot.title}\n"
            f"💰 Текущая цена: <b>{lot.current_price:,.2f} ₽</b>\n"
            f"📈 Минимальная следующая ставка: <b>{min_bid_amount:,.2f} ₽</b>\n"
            f"{leader_text}"
            f"Введите сумму автоставки, до которой система будет автоматически повышать вашу ставку."
            f"{existing_text}"
        )

        # Сохраняем состояние и ждем ввода суммы
        await state.update_data(lot_id=lot_id, message_id=callback.message.message_id)
        await state.set_state(BidStates.waiting_for_max_bid_amount)

        # Кнопка Назад к лоту
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        back_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔙 Назад к лоту", callback_data=f"lot_details:{lot_id}"
                    )
                ]
            ]
        )

        # Безопасное редактирование сообщения
        try:
            await callback.message.edit_text(
                text, parse_mode="HTML", reply_markup=back_keyboard
            )
        except Exception as e:
            if "there is no text in the message to edit" in str(e).lower():
                try:
                    await callback.message.edit_caption(
                        caption=text, parse_mode="HTML", reply_markup=back_keyboard
                    )
                except Exception:
                    await callback.message.answer(
                        text, parse_mode="HTML", reply_markup=back_keyboard
                    )
            else:
                raise e

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при запуске автоставки: {e}")
        await callback.answer("❌ Ошибка при запуске автоставки")
    finally:
        db.close()


async def ensure_user_registered(message: Message) -> User:
    """Обеспечивает регистрацию пользователя в базе данных"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()

        if not user:
            # Создаем нового пользователя
            user = User(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
                role=UserRole.SELLER,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info(f"Зарегистрирован новый пользователь: {user.telegram_id}")

        # Проверяем, заблокирован ли пользователь
        if user.is_banned:
            await message.answer(
                "❌ **Доступ запрещен!**\n\n"
                "Ваш аккаунт заблокирован администратором.\n"
                "Обратитесь к администратору для разблокировки.",
                parse_mode="Markdown",
            )
            return None

        return user
    except Exception as e:
        logger.error(f"Ошибка при регистрации пользователя: {e}")
        return None
    finally:
        db.close()


@router.message(Command("my_bids"))
async def my_bids(message: Message, state: FSMContext):
    """Показать мои ставки"""
    # Очищаем состояние FSM, если пользователь был в процессе ввода ставки
    from bot.utils.fsm_utils import clear_bid_state_if_needed

    if await clear_bid_state_if_needed(state):
        logger.info(
            f"Очищено состояние FSM для пользователя {message.from_user.id} при команде /my_bids"
        )

    # Регистрируем пользователя
    user = await ensure_user_registered(message)
    if not user:
        await message.answer("❌ Ошибка при регистрации пользователя")
        return

    db = SessionLocal()
    try:

        # Получаем ставки пользователя
        user_bids = (
            db.query(Bid)
            .filter(Bid.bidder_id == user.id)
            .order_by(Bid.created_at.desc())
            .limit(10)
            .all()
        )

        if not user_bids:
            await message.answer(
                "📋 **Мои ставки**\n\n"
                "У вас пока нет ставок.\n"
                f"Найдите интересные лоты в канале @{TELEGRAM_CHANNEL_USERNAME} и сделайте ставку!"
            )
            return

        text = "📋 **Мои последние ставки:**\n\n"
        for bid in user_bids:
            lot = db.query(Lot).filter(Lot.id == bid.lot_id).first()
            if lot:
                # Определяем статус лота
                if lot.status == LotStatus.SOLD:
                    # Проверяем, выиграл ли пользователь
                    max_bid = (
                        db.query(Bid)
                        .filter(Bid.lot_id == bid.lot_id)
                        .order_by(Bid.amount.desc())
                        .first()
                    )
                    if max_bid and max_bid.bidder_id == user.id:
                        status = "🏆 Выиграл"
                        status_emoji = "🏆"
                    else:
                        status = "💸 Проиграл"
                        status_emoji = "💸"
                elif lot.status == LotStatus.ACTIVE and (
                    lot.end_time is None
                    or lot.end_time > get_moscow_time().replace(tzinfo=None)
                ):
                    status = "🔄 Активен"
                    status_emoji = "🔄"
                else:
                    status = "⏰ Завершен"
                    status_emoji = "⏰"

                text += f"{status_emoji} **{lot.title}**\n"
                text += f"💰 Ставка: {bid.amount:,.2f} ₽\n"
                text += f"📊 Текущая цена: {lot.current_price:,.2f} ₽\n"
                text += f"📅 Дата ставки: {bid.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                text += f"🤖 Авто: {'Да' if bid.is_auto_bid else 'Нет'}\n"
                text += f"📊 Статус: {status}\n\n"

        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка при получении ставок: {e}")
        await message.answer("❌ Ошибка при получении данных")
    finally:
        db.close()


# Удаляем дублирующийся обработчик - основной обработчик my_bids уже есть выше


@router.callback_query(F.data.startswith("quick_bid:"))
async def quick_bid(callback: CallbackQuery):
    """Быстрая ставка"""
    # Проверяем блокировку
    if await check_user_banned_callback(callback):
        return

    db = SessionLocal()
    try:
        parts = callback.data.split(":")
        lot_id = int(parts[1])
        selected_amount = None
        if len(parts) >= 3:
            try:
                selected_amount = float(parts[2])
            except ValueError:
                selected_amount = None
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        lot = db.query(Lot).filter(Lot.id == lot_id).first()

        if not user or not lot:
            await callback.answer("❌ Лот или пользователь не найден")
            return

        # Проверяем, активен ли лот
        if lot.status != LotStatus.ACTIVE or (
            lot.end_time is not None
            and lot.end_time <= get_moscow_time().replace(tzinfo=None)
        ):
            await callback.answer("❌ Аукцион завершен")
            return

        # Запретить ставку для продавца на свой лот
        if lot.seller_id == user.id:
            await callback.answer(
                "❌ Вы не можете делать ставки на свой собственный лот"
            )
            return

        # Рассчитываем минимальную ставку
        min_bid_amount = calculate_min_bid(lot.current_price)
        min_increment = min_bid_amount - lot.current_price

        # Определяем сумму ставки: берём выбранную пользователем, но не ниже минимума
        bid_amount_to_place = (
            selected_amount
            if selected_amount and selected_amount >= min_bid_amount
            else min_bid_amount
        )

        # Получаем информацию о текущем лидере (до новой ставки)
        leader_info_before = get_current_leader(db, lot.id)
        leader_text_before = ""
        if leader_info_before and leader_info_before[0]:
            if leader_info_before[1] is not None:
                leader_text_before = f"🥇 <b>Текущий лидер:</b> {leader_info_before[0]} ({leader_info_before[1]:,.2f} ₽)\n"
            else:
                leader_text_before = (
                    f"🥇 <b>Текущий лидер:</b> {leader_info_before[0]}\n"
                )

        # Фиксируем предыдущего лидера до создания новой ставки
        previous_top_bid = (
            db.query(Bid)
            .filter(Bid.lot_id == lot_id)
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
            logger.info(f"Аукцион {lot_id} автоматически продлен до {lot.end_time}")

        # Создаем ставку
        new_bid = Bid(
            lot_id=lot_id,
            bidder_id=user.id,
            amount=bid_amount_to_place,
            is_auto_bid=False,
        )

        db.add(new_bid)
        lot.current_price = bid_amount_to_place
        db.commit()

        # Запускаем автоставки после пользовательской ставки
        try:
            AutoBidManager.process_new_bid(lot_id, bid_amount_to_place, user.id)
        except Exception as e:
            logger.error(
                f"Ошибка автоповышения ставок после пользовательской ставки: {e}"
            )

        # Логируем успешное создание ставки
        logger.info(
            f"Ставка успешно создана: лот {lot_id}, пользователь {user.id}, сумма {bid_amount_to_place}"
        )

        # Уведомляем о продлении аукциона, если произошло
        if auction_extended:
            await notification_service.notify_auction_extended(
                lot_id, old_end_time, lot.end_time
            )

        # Сообщение в канале обновится автоматически через AutoBidManager при значительных изменениях

        # Пересчитываем лидера после успешной ставки
        leader_info_after = get_current_leader(db, lot.id)
        leader_text = ""
        if leader_info_after and leader_info_after[0]:
            if leader_info_after[1] is not None:
                leader_text = f"🥇 <b>Текущий лидер:</b> {leader_info_after[0]} ({leader_info_after[1]:,.2f} ₽)\n"
            else:
                leader_text = f"🥇 <b>Текущий лидер:</b> {leader_info_after[0]}\n"

        # Уведомляем предыдущего лидера (если есть и это не текущий пользователь)
        if previous_top_bid and previous_top_bid.bidder_id != user.id:
            await notification_service.notify_outbid(
                lot_id, previous_top_bid.bidder_id, bid_amount_to_place
            )

        # Автоставки не запускаем автоматически при ставке пользователя

        # Канал не обновляем из бота, чтобы не менять посты при пользовательских действиях

        # Формируем текст ответа
        result_text = (
            f"✅ <b>Ставка принята!</b>\n\n"
            f"🏷️ Лот: {lot.title}\n"
            f"💰 Сумма: {bid_amount_to_place:,.2f} ₽\n"
            f"{leader_text}"
            f"📊 Статус: Применена\n\n"
            f"ℹ️ Ваша ставка стала текущей ценой"
        )
        # Кнопка Назад к лоту
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        back_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✏️ Изменить автоставку",
                        callback_data=f"change_auto_bid:{lot_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔙 Назад к лоту", callback_data=f"lot_details:{lot_id}"
                    )
                ],
            ]
        )

        # Безопасное редактирование сообщения (может содержать изображение)
        try:
            await callback.message.edit_text(
                result_text, parse_mode="HTML", reply_markup=back_keyboard
            )
        except Exception as e:
            if "there is no text in the message to edit" in str(e).lower():
                # Если сообщение содержит изображение, редактируем подпись
                try:
                    await callback.message.edit_caption(
                        caption=result_text,
                        parse_mode="HTML",
                        reply_markup=back_keyboard,
                    )
                except Exception:
                    # В крайнем случае отправляем новое сообщение
                    await callback.message.answer(
                        result_text, parse_mode="HTML", reply_markup=back_keyboard
                    )
            else:
                raise e

    except Exception as e:
        logger.error(f"Ошибка при быстрой ставке: {e}")
        await callback.answer("❌ Ошибка при создании ставки")
    finally:
        db.close()


@router.callback_query(F.data.startswith("custom_bid:"))
async def custom_bid(callback: CallbackQuery, state: FSMContext):
    """Запрос на ввод кастомной ставки"""
    # Проверяем блокировку
    if await check_user_banned_callback(callback):
        return

    db = SessionLocal()
    try:
        lot_id = int(callback.data.split(":")[1])
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        lot = db.query(Lot).filter(Lot.id == lot_id).first()

        if not user or not lot:
            await callback.answer("❌ Лот или пользователь не найден")
            return

        # Проверяем, активен ли лот
        if lot.status != LotStatus.ACTIVE or (
            lot.end_time is not None
            and lot.end_time <= get_moscow_time().replace(tzinfo=None)
        ):
            await callback.answer("❌ Аукцион завершен")
            return

        # Запретить ставку для продавца на свой лот
        if lot.seller_id == user.id:
            await callback.answer(
                "❌ Вы не можете делать ставки на свой собственный лот"
            )
            return

        # Сохраняем данные в состоянии
        await state.update_data(lot_id=lot_id, message_id=callback.message.message_id)
        await state.set_state(BidStates.waiting_for_bid_amount)

        # Рассчитываем минимальную ставку
        min_bid_amount = calculate_min_bid(lot.current_price)

        # Получаем информацию о текущем лидере
        leader_info = get_current_leader(db, lot.id)
        leader_text = ""
        if leader_info and leader_info[0]:
            if leader_info[1] is not None:
                leader_text = f"🥇 <b>Текущий лидер:</b> {leader_info[0]} ({leader_info[1]:,.2f} ₽)\n"
            else:
                leader_text = f"🥇 <b>Текущий лидер:</b> {leader_info[0]}\n"

        # Создаем текст сообщения
        text = (
            f"💰 <b>Введите сумму ставки</b>\n\n"
            f"🏷️ Лот: {lot.title}\n"
            f"💰 Текущая цена: <b>{lot.current_price:,.2f} ₽</b>\n"
            f"📈 Минимальная ставка: <b>{min_bid_amount:,.2f} ₽</b>\n"
            f"{leader_text}"
            f"💡 Введите сумму больше минимальной ставки"
        )

        # Кнопка Назад
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        back_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔙 Назад к лоту", callback_data=f"lot_details:{lot_id}"
                    )
                ]
            ]
        )
        # Для подтверждения настройки автоставки ниже уже добавлена кнопка изменения

        # Безопасное редактирование сообщения (может содержать изображение)
        try:
            await callback.message.edit_text(
                text, parse_mode="HTML", reply_markup=back_keyboard
            )
        except Exception as e:
            if "there is no text in the message to edit" in str(e).lower():
                # Если сообщение содержит изображение, редактируем подпись
                try:
                    await callback.message.edit_caption(
                        caption=text, parse_mode="HTML", reply_markup=back_keyboard
                    )
                except Exception:
                    # В крайнем случае отправляем новое сообщение
                    await callback.message.answer(
                        text, parse_mode="HTML", reply_markup=back_keyboard
                    )
            else:
                raise e

        # Live-обновления убраны для улучшения производительности

    except Exception as e:
        logger.error(f"Ошибка при запросе кастомной ставки: {e}")
        await callback.answer("❌ Ошибка при создании ставки")
    finally:
        db.close()


@router.message(BidStates.waiting_for_bid_amount)
async def process_custom_bid(message: Message, state: FSMContext):
    """Обработка введенной пользователем ставки"""
    # Проверяем блокировку
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if user and user.is_banned:
            await message.answer(
                "❌ **Доступ запрещен!**\n\n"
                "Ваш аккаунт заблокирован администратором.\n"
                "Обратитесь к администратору для разблокировки.",
                parse_mode="Markdown",
            )
            await state.clear()
            return
    except Exception as e:
        logger.error(f"Ошибка при проверке блокировки: {e}")
    finally:
        db.close()

    # Получаем данные из состояния
    data = await state.get_data()
    lot_id = data.get("lot_id")
    message_id = data.get("message_id")

    if not lot_id:
        await message.answer("❌ Ошибка: лот не найден")
        await state.clear()
        return

    db = SessionLocal()
    try:
        # Получаем лот и пользователя
        lot = db.query(Lot).filter(Lot.id == lot_id).first()
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()

        if not lot or not user:
            await message.answer("❌ Лот или пользователь не найден")
            await state.clear()
            return

        # Проверяем, активен ли лот
        if lot.status != LotStatus.ACTIVE or (
            lot.end_time is not None
            and lot.end_time <= get_moscow_time().replace(tzinfo=None)
        ):
            await message.answer("❌ Аукцион завершен")
            await state.clear()
            return

        # Запретить ставку для продавца на свой лот
        if lot.seller_id == user.id:
            await message.answer(
                "❌ Вы не можете делать ставки на свой собственный лот"
            )
            await state.clear()
            return

        # Парсим введенную сумму
        try:
            bid_amount = float(message.text.replace(",", ".").replace(" ", ""))
        except ValueError:
            await message.answer(
                "❌ Неверный формат суммы. Введите число (например: 1000)"
            )
            return

        # Рассчитываем минимальную ставку
        min_bid_amount = calculate_min_bid(lot.current_price)

        # Проверяем, что ставка больше минимальной
        if bid_amount < min_bid_amount:
            await message.answer(
                f"❌ Сумма слишком мала. Минимальная ставка: {min_bid_amount:,.2f} ₽"
            )
            return

        # Получаем информацию о текущем лидере
        leader_info = get_current_leader(db, lot.id)
        leader_text = ""
        if leader_info and leader_info[0]:
            if leader_info[1] is not None:
                leader_text = f"🥇 <b>Текущий лидер:</b> @{leader_info[0]} ({leader_info[1]:,.2f} ₽)\n"
            else:
                leader_text = f"🥇 <b>Текущий лидер:</b> @{leader_info[0]}\n"

        # Фиксируем предыдущего лидера до создания новой ставки
        previous_top_bid = (
            db.query(Bid)
            .filter(Bid.lot_id == lot_id)
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
            logger.info(f"Аукцион {lot_id} автоматически продлен до {lot.end_time}")

        # Создаем ставку
        new_bid = Bid(
            lot_id=lot_id,
            bidder_id=user.id,
            amount=bid_amount,
            is_auto_bid=False,
        )

        db.add(new_bid)
        lot.current_price = bid_amount
        db.commit()

        # Запускаем автоставки после пользовательской ставки
        try:
            AutoBidManager.process_new_bid(lot_id, bid_amount, user.id)
        except Exception as e:
            logger.error(
                f"Ошибка автоповышения ставок после пользовательской ставки: {e}"
            )

        # Логируем успешное создание ставки
        logger.info(
            f"Ставка успешно создана: лот {lot_id}, пользователь {user.id}, сумма {bid_amount}"
        )

        # Уведомляем о продлении аукциона, если произошло
        if auction_extended:
            await notification_service.notify_auction_extended(
                lot_id, old_end_time, lot.end_time
            )

        # Сообщение в канале обновится автоматически через AutoBidManager при значительных изменениях

        # Пересчитываем лидера после ставки
        leader_info_after = get_current_leader(db, lot.id)
        leader_text = ""
        if leader_info_after and leader_info_after[0]:
            if leader_info_after[1] is not None:
                leader_text = f"🥇 <b>Текущий лидер:</b> {leader_info_after[0]} ({leader_info_after[1]:,.2f} ₽)\n"
            else:
                leader_text = f"🥇 <b>Текущий лидер:</b> {leader_info_after[0]}\n"

        # Уведомляем предыдущего лидера (если есть и это не текущий пользователь)
        if previous_top_bid and previous_top_bid.bidder_id != user.id:
            await notification_service.notify_outbid(
                lot_id, previous_top_bid.bidder_id, bid_amount
            )

        # Автоставки не запускаем автоматически при ставке пользователя

        # Канал не обновляем из бота, чтобы не менять посты при пользовательских действиях

        # Формируем текст ответа
        result_text = (
            f"✅ <b>Ставка принята!</b>\n\n"
            f"🏷️ Лот: {lot.title}\n"
            f"💰 Сумма: {bid_amount:,.2f} ₽\n"
            f"{leader_text}"
            f"📊 Статус: Применена\n\n"
            f"ℹ️ Ваша ставка стала текущей ценой"
        )

        # Кнопка Назад к лоту; редактируем исходное сообщение с запросом суммы
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        back_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔙 Назад к лоту", callback_data=f"lot_details:{lot_id}"
                    )
                ]
            ]
        )

        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=message_id,
                text=result_text,
                reply_markup=back_keyboard,
                parse_mode="HTML",
            )
            # Удаляем ввод пользователя, чтобы избежать дублей
            try:
                await message.delete()
            except Exception:
                pass
        except Exception:
            # Фолбэк: отправляем новое сообщение
            await message.answer(
                result_text, parse_mode="HTML", reply_markup=back_keyboard
            )

        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка при обработке кастомной ставки: {e}")
        await message.answer("❌ Ошибка при создании ставки")
        await state.clear()
    finally:
        db.close()


@router.message(BidStates.waiting_for_max_bid_amount)
async def process_auto_bid_amount(message: Message, state: FSMContext):
    """Обработка суммы автоставки для конкретного лота"""
    # Проверяем блокировку
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if user and user.is_banned:
            await message.answer(
                "❌ **Доступ запрещен!**\n\n"
                "Ваш аккаунт заблокирован администратором.\n"
                "Обратитесь к администратору для разблокировки.",
                parse_mode="Markdown",
            )
            await state.clear()
            return
    except Exception as e:
        logger.error(f"Ошибка при проверке блокировки: {e}")
    finally:
        db.close()

    # Получаем данные из состояния
    data = await state.get_data()
    lot_id = data.get("lot_id")
    message_id = data.get("message_id")

    if not lot_id:
        await message.answer("❌ Ошибка: лот не найден")
        await state.clear()
        return

    db = SessionLocal()
    try:
        # Получаем лот и пользователя
        lot = db.query(Lot).filter(Lot.id == lot_id).first()
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()

        if not lot or not user:
            await message.answer("❌ Лот или пользователь не найден")
            await state.clear()
            return

        # Проверяем, активен ли лот
        if lot.status != LotStatus.ACTIVE or (
            lot.end_time is not None
            and lot.end_time <= get_moscow_time().replace(tzinfo=None)
        ):
            await message.answer("❌ Аукцион завершен")
            await state.clear()
            return

        # Запретить автоставку для продавца на свой лот
        if lot.seller_id == user.id:
            await message.answer(
                "❌ Вы не можете использовать автоставку на свой собственный лот"
            )
            await state.clear()
            return

        # Парсим введенную сумму
        try:
            target_amount = float(message.text.replace(",", ".").replace(" ", ""))
        except ValueError:
            await message.answer(
                "❌ Неверный формат суммы. Введите число (например: 10000)"
            )
            return

        # Проверяем автоставку с уведомлениями о текущем лидере
        check_result = AutoBidManager.check_auto_bid_with_notifications(
            user.id, lot.id, target_amount
        )

        if not check_result["can_set"]:
            await message.answer(f"❌ {check_result['message']}")
            return

        # Получаем информацию о текущем лидере для отображения
        leader_text = ""
        if (
            check_result["current_leader_name"]
            and check_result["current_leader_name"] != "Нет лидера"
        ):
            leader_text = f"🥇 <b>Текущий лидер:</b> {check_result['current_leader_name']} ({check_result['current_leader_amount']:,.2f} ₽)\n"

        # Устанавливаем автоставку
        success = AutoBidManager.set_auto_bid(user.id, lot.id, target_amount)

        if success:
            # После установки — принудительно пересчитаем автоставки и обновим данные лота
            try:
                AutoBidManager.recalculate_auto_bids_for_lot(lot.id)
            except Exception as e:
                logger.error(f"Ошибка пересчета автоставок после установки: {e}")

            # Обновляем объект лота и лидера из БД
            db.refresh(lot)
            leader_info_after = get_current_leader(db, lot.id)
            leader_text_after = ""
            if leader_info_after and leader_info_after[0]:
                if leader_info_after[1] is not None:
                    leader_text_after = f"🥇 <b>Текущий лидер:</b> {leader_info_after[0]} ({leader_info_after[1]:,.2f} ₽)\n"
                else:
                    leader_text_after = (
                        f"🥇 <b>Текущий лидер:</b> {leader_info_after[0]}\n"
                    )

            # Получаем существующую автоставку для отображения
            existing_auto_bid = AutoBidManager.get_user_auto_bid(user.id, lot.id)
            if existing_auto_bid:
                auto_bid_text = f"🤖 <b>Ваша автоставка:</b> {existing_auto_bid.target_amount:,.2f} ₽"
            else:
                auto_bid_text = (
                    f"🤖 <b>Автоставка установлена:</b> {target_amount:,.2f} ₽"
                )

            response_text = (
                f"✅ <b>Автоставка успешно установлена!</b>\n\n"
                f"📦 <b>Лот:</b> {lot.title}\n"
                f"💰 <b>Текущая цена:</b> {lot.current_price:,.2f} ₽\n"
                f"{leader_text_after}"
                f"{auto_bid_text}\n\n"
                f"<i>Система будет автоматически повышать вашу ставку до указанной суммы при появлении новых ставок.</i>"
            )

            await message.answer(response_text, parse_mode="HTML")

            # Сообщение в канале обновится автоматически через AutoBidManager
        else:
            await message.answer(
                "❌ Ошибка при установке автоставки. Попробуйте еще раз."
            )

        # Очищаем состояние
        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка при обработке автоставки: {e}")
        await message.answer("❌ Произошла ошибка при установке автоставки")
        await state.clear()
    finally:
        db.close()


@router.message(BidStates.waiting_for_bid_amount)
async def invalid_bid_input(message: Message, state: FSMContext):
    """Обработка невалидного ввода ставки"""
    await message.answer(
        "❌ Некорректный ввод. Введите только число (например: 1000 или 1000.50) без лишних символов, букв, пробелов или валюты."
    )
