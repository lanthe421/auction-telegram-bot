import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func

from bot.handlers.bid_states import BalanceStates, BidStates
from bot.utils.finance_manager import finance_manager

# from bot.utils.finance_manager import finance_manager
from bot.utils.keyboards import get_main_keyboard, get_user_profile_keyboard
from bot.utils.time_utils import get_moscow_time
from config.settings import (  # AUTO_BID_MIN_BALANCE,; TELEGRAM_CHANNEL_USERNAME,
    ADMIN_IDS,
    AUTO_BID_MIN_PAYMENTS,
    SUPER_ADMIN_IDS,
    SUPPORT_IDS,
)
from database.db import SessionLocal
from database.models import Bid, Lot, LotStatus, Payment, User, UserRole

# from datetime import datetime


# from management.core.telegram_publisher_sync import telegram_publisher_sync

router = Router()
logger = logging.getLogger(__name__)


async def check_user_banned(message: Message) -> bool:
    """Проверяет, заблокирован ли пользователь"""
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
            return True
        return False
    except Exception as e:
        logger.error(f"Ошибка при проверке блокировки пользователя: {e}")
        return False
    finally:
        db.close()


async def check_user_banned_callback(callback: CallbackQuery) -> bool:
    """Проверяет, заблокирован ли пользователь (для callback)"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        logger.info(
            "Проверка блокировки для пользователя %s: user=%s, is_banned=%s",
            callback.from_user.id,
            user,
            (user.is_banned if user else "None"),
        )

        if not user:
            logger.warning(
                f"Пользователь {callback.from_user.id} не найден в базе данных"
            )
            return False

        if user.is_banned:
            logger.info(
                f"Пользователь {callback.from_user.id} заблокирован, показываем уведомление"
            )
            await callback.answer(
                "❌ Ваш аккаунт заблокирован администратором", show_alert=True
            )
            return True
        else:
            logger.info(f"Пользователь {callback.from_user.id} не заблокирован")
            return False
    except Exception as e:
        logger.error(f"Ошибка при проверке блокировки пользователя: {e}")
        return False
    finally:
        db.close()


def allow_auto_bid_for_test_user(user, db):
    test_ids = {1063712346, 1196965399}
    if user.telegram_id in test_ids:
        # Для тестовых пользователей только обеспечиваем выполнение порога успешных покупок,
        # не меняя вручную выбор пользователя по автоставкам
        if user.successful_payments < AUTO_BID_MIN_PAYMENTS:
            user.successful_payments = AUTO_BID_MIN_PAYMENTS
            db.commit()


async def _safe_edit_text(
    message_obj, text: str, reply_markup=None, parse_mode: str = "HTML"
):
    """Безопасное редактирование: сначала пробуем редактировать текст,
    при ошибке для медиа — редактируем подпись, в крайнем случае отправляем новое сообщение.
    """
    try:
        await message_obj.edit_text(
            text, parse_mode=parse_mode, reply_markup=reply_markup
        )
        return
    except Exception as e:
        err = str(e).lower()
        if "message is not modified" in err:
            return
        # Сообщение без текстового блока (например, фото) — редактируем подпись
        if (
            "there is no text in the message to edit" in err
            or "message to edit has no text" in err
        ):
            try:
                await message_obj.edit_caption(
                    caption=text, parse_mode=parse_mode, reply_markup=reply_markup
                )
                return
            except Exception as cap_err:
                if "message is not modified" in str(cap_err).lower():
                    return
                # падаем в общий фолбэк ниже
        # Логируем только неожиданную ошибку и шлём новое сообщение
        logger.error(f"Ошибка при редактировании сообщения: {e}")
        try:
            await message_obj.answer(
                text, parse_mode=parse_mode, reply_markup=reply_markup
            )
        except Exception as inner_e:
            logger.error(f"Ошибка при отправке нового сообщения: {inner_e}")


async def _safe_callback_answer(callback: CallbackQuery, text: str):
    try:
        await callback.answer(text)
    except Exception as e:
        if "query is too old" in str(e).lower():
            return
        logger.error(f"Ошибка при ответе на callback: {e}")


@router.message(Command("profile"))
async def user_profile(message: Message):
    """Личный кабинет пользователя"""
    # Проверяем блокировку
    if await check_user_banned(message):
        return

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
        allow_auto_bid_for_test_user(user, db)

        # Проверяем, заблокирован ли пользователь
        if user.is_banned:
            await message.answer(
                "❌ **Доступ запрещен!**\n\n"
                "Ваш аккаунт заблокирован администратором.\n"
                "Обратитесь к администратору для разблокировки.",
                parse_mode="Markdown",
            )
            return

        # Определяем роль пользователя
        role_text = "👤 Пользователь"
        if user.telegram_id in SUPER_ADMIN_IDS:
            role_text = "👑 Супер администратор"
        elif user.telegram_id in ADMIN_IDS:
            role_text = "⚙️ Администратор"
        elif user.telegram_id in SUPPORT_IDS:
            role_text = "🔧 Поддержка"

        # Статистика пользователя
        user_bids = db.query(Bid).filter(Bid.bidder_id == user.id).count()

        text = f"""👤 **Личный кабинет**

**Основная информация:**
👤 Имя: {user.first_name} {user.last_name or ''}
🔗 Username: @{user.username or 'N/A'}
🎭 Роль: {role_text}

**Статистика:**
💰 Сделанных ставок: {user_bids}
💳 Успешных покупок: {user.successful_payments}
⚠️ Страйков: {user.strikes}/3

**Статус аккаунта:** {'✅ Активен' if not user.is_banned else '❌ Заблокирован'}"""

        await message.answer(text, reply_markup=get_user_profile_keyboard())

    except Exception as e:
        logger.error(f"Ошибка при получении профиля пользователя: {e}")
        await message.answer("❌ Ошибка при получении данных профиля")
    finally:
        db.close()


@router.callback_query(F.data == "top_up_balance")
async def top_up_balance(callback: CallbackQuery):
    """Запрос суммы для пополнения баланса пользователя в боте (без реальной оплаты)."""
    # Проверяем блокировку
    if await check_user_banned_callback(callback):
        return
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not user:
            await callback.answer("❌ Пользователь не найден")
            return

        await callback.message.edit_text(
            (
                f"💳 <b>Пополнение баланса</b>\n\n"
                f"Текущий баланс: <b>{user.balance:,.2f} ₽</b>\n\n"
                f"Введите сумму пополнения (только число)."
            ),
            parse_mode="HTML",
        )
        await callback.answer("Введите сумму пополнения")
        # Предлагаем перейти на экран с выбором действий по балансу
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="➕ Пополнить", callback_data="start_top_up"
                    ),
                    InlineKeyboardButton(
                        text="➖ Вывести", callback_data="start_withdraw"
                    ),
                ]
            ]
        )
        await callback.message.edit_text(
            f"💳 <b>Ваш баланс</b>\n\nТекущий баланс: <b>{user.balance:,.2f} ₽</b>\n\nВыберите действие:",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.error(f"Ошибка начала пополнения баланса: {e}")
    finally:
        db.close()


@router.message(F.text == "💳 Мой баланс")
async def show_my_balance(message: Message, state: FSMContext):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            await message.answer("❌ Пользователь не найден")
            return
        text = (
            f"💳 <b>Ваш баланс</b>\n\n"
            f"Текущий баланс: <b>{user.balance:,.2f} ₽</b>\n\n"
            f"Выберите действие:"
        )
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="➕ Пополнить", callback_data="start_top_up"
                    ),
                    InlineKeyboardButton(
                        text="➖ Вывести", callback_data="start_withdraw"
                    ),
                ]
            ]
        )
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    finally:
        db.close()


@router.message(BalanceStates.waiting_for_top_up_amount)
async def process_top_up_amount(message: Message, state: FSMContext):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            await message.answer("❌ Пользователь не найден")
            await state.clear()
            return
        try:
            amount = float(message.text.replace(",", ".").replace(" ", ""))
        except ValueError:
            await message.answer("❌ Неверный формат. Введите число, например: 500")
            return
        if amount <= 0:
            await message.answer("❌ Сумма должна быть больше 0. Отменено.")
            await state.clear()
            return

        # Пополняем баланс (без реальной оплаты)
        success = finance_manager.add_balance(user.id, amount, "Пополнение через бота")
        if not success:
            await message.answer("❌ Не удалось пополнить баланс")
            await state.clear()
            return

        # Перечитываем обновленный баланс
        db.refresh(user)
        await message.answer(
            f"✅ Баланс пополнен на {amount:,.2f} ₽\nТекущий баланс: {user.balance:,.2f} ₽"
        )
        await state.clear()
    except Exception as e:
        logger.error(f"Ошибка при пополнении баланса: {e}")
        await message.answer("❌ Произошла ошибка при пополнении")
        await state.clear()
    finally:
        db.close()


@router.callback_query(F.data == "start_top_up")
async def start_top_up(callback: CallbackQuery, state: FSMContext):
    if await check_user_banned_callback(callback):
        return
    await callback.message.edit_text("💳 Введите сумму пополнения (число)")
    await state.set_state(BalanceStates.waiting_for_top_up_amount)
    await callback.answer()


@router.callback_query(F.data == "start_withdraw")
async def start_withdraw(callback: CallbackQuery, state: FSMContext):
    if await check_user_banned_callback(callback):
        return
    await callback.message.edit_text("💳 Введите сумму для вывода (число)")
    await state.set_state(BalanceStates.waiting_for_withdraw_amount)
    await callback.answer()


@router.message(BalanceStates.waiting_for_withdraw_amount)
async def process_withdraw_amount(message: Message, state: FSMContext):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            await message.answer("❌ Пользователь не найден")
            await state.clear()
            return
        try:
            amount = float(message.text.replace(",", ".").replace(" ", ""))
        except ValueError:
            await message.answer("❌ Неверный формат. Введите число, например: 500")
            return
        if amount <= 0:
            await message.answer("❌ Сумма должна быть больше 0. Отменено.")
            await state.clear()
            return
        success = finance_manager.deduct_balance(
            user.id, amount, "Вывод средств через бота (демо)"
        )
        if not success:
            await message.answer("❌ Недостаточно средств или ошибка")
            await state.clear()
            return
        db.refresh(user)
        await message.answer(
            f"✅ Заявка на вывод на сумму {amount:,.2f} ₽ оформлена (демо).\nТекущий баланс: {user.balance:,.2f} ₽"
        )
        await state.clear()
    except Exception as e:
        logger.error(f"Ошибка при выводе средств: {e}")
        await message.answer("❌ Произошла ошибка при выводе")
        await state.clear()
    finally:
        db.close()


def get_auto_bid_settings_text_and_keyboard(user):
    status = "✅ Включены" if user.auto_bid_enabled else "❌ Отключены"
    action = "Отключить" if user.auto_bid_enabled else "Включить"
    action_data = "disable_auto_bid" if user.auto_bid_enabled else "enable_auto_bid"
    text = f"""
🤖 **Настройки автоставок**

**Текущий статус:** {status}

**Условия для активации:**
💳 Минимум успешных покупок: {AUTO_BID_MIN_PAYMENTS}

**Ваш прогресс:**
💳 Успешных покупок: {user.successful_payments} {'✅' if user.successful_payments >= AUTO_BID_MIN_PAYMENTS else '❌'}

**Функции автоставок:**
• Автоматическое повышение ставок
• Уведомления о новых ставках
• Защита от перебивания
    """
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{action} автоставки", callback_data=action_data
                )
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_settings")],
        ]
    )
    return text, keyboard


@router.callback_query(F.data == "auto_bid_settings")
async def auto_bid_settings(callback: CallbackQuery):
    """Настройки автоставок"""
    # Проверяем блокировку
    if await check_user_banned_callback(callback):
        return

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        allow_auto_bid_for_test_user(user, db)
        text, keyboard = get_auto_bid_settings_text_and_keyboard(user)
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Ошибка при настройке автоставок: {e}")
        await callback.answer("❌ Ошибка при получении настроек")
    finally:
        db.close()


@router.callback_query(F.data.startswith("toggle_auto_bid:"))
async def toggle_auto_bid_inline(callback: CallbackQuery):
    """Переключение автоставок только через экран ⚙️ Настройки."""
    # Проверяем блокировку
    if await check_user_banned_callback(callback):
        return

    try:
        await callback.answer("Изменение автоставок доступно в ⚙️ Настройки")
        # Переходим в настройки
        await show_settings(callback.message)
    except Exception as e:
        logger.error(f"Ошибка перенаправления в настройки: {e}")
        await callback.answer("❌ Ошибка")


@router.callback_query(F.data == "my_participation")
async def show_my_participation(callback: CallbackQuery):
    """Показывает участие пользователя в аукционах (ставки и покупки) с пагинацией"""
    logger.info(
        "=== НАЧАЛО show_my_participation для пользователя %s ===",
        callback.from_user.id,
    )

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        logger.info(f"Пользователь найден: {user}")

        if not user:
            logger.warning(
                f"Пользователь {callback.from_user.id} не найден в базе данных"
            )
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return

        logger.info(f"Статус is_banned: {user.is_banned}")

        # Простая и прямая проверка блокировки
        if user.is_banned:
            logger.info("ПОЛЬЗОВАТЕЛЬ ЗАБЛОКИРОВАН! Показываем уведомление")
            await callback.answer(
                "❌ Ваш аккаунт заблокирован администратором", show_alert=True
            )
            return
        else:
            logger.info("Пользователь НЕ заблокирован, продолжаем")

        # Рисуем страницу 1
        text, keyboard = _build_my_participation_page(db, user, page=1, per_page=5)
        logger.info("Показываем участие пользователю %s (стр.1)", callback.from_user.id)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка при получении участия пользователя: {e}")
        await callback.answer("❌ Ошибка при получении данных")
    finally:
        db.close()
        logger.info(
            "=== КОНЕЦ show_my_participation для пользователя %s ===",
            callback.from_user.id,
        )


def _build_my_participation_page(db, user, page: int = 1, per_page: int = 5):
    """Строит текст и клавиатуру для раздела "Мое участие" с пагинацией"""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    # Получаем лоты, на которые пользователь делал ставки
    user_bids = db.query(Bid).filter(Bid.bidder_id == user.id).all()
    participated_lots = list({bid.lot_id for bid in user_bids})

    lots_info = []
    for lot_id in participated_lots:
        lot = db.query(Lot).filter(Lot.id == lot_id).first()
        if not lot:
            continue
        last_bid = (
            db.query(Bid)
            .filter(Bid.lot_id == lot_id, Bid.bidder_id == user.id)
            .order_by(Bid.created_at.desc())
            .first()
        )
        if lot.status == LotStatus.SOLD:
            winning_bid = (
                db.query(Bid)
                .filter(Bid.lot_id == lot_id)
                .order_by(Bid.amount.desc())
                .first()
            )
            if winning_bid and winning_bid.bidder_id == user.id:
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

        lots_info.append(
            {
                "lot": lot,
                "last_bid": last_bid,
                "status": status,
                "status_emoji": status_emoji,
            }
        )

    if not lots_info:
        empty_text = (
            "📦 <b>Мое участие в аукционах</b>\n\n"
            "Вы пока не участвовали ни в одном аукционе.\n"
            "Найдите интересные лоты в канале и сделайте ставку!"
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")]
            ]
        )
        return empty_text, keyboard

    # Сортируем по дате последней ставки
    lots_info.sort(
        key=lambda x: (
            x["last_bid"].created_at if x["last_bid"] else x["lot"].created_at
        ),
        reverse=True,
    )

    total_items = len(lots_info)
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page
    page_items = lots_info[start:end]

    text_lines = ["📦 <b>Мое участие в аукционах</b>\n"]
    for info in page_items:
        lot = info["lot"]
        last_bid = info["last_bid"]
        text_lines.append(f"{info['status_emoji']} <b>{lot.title}</b>")
        if last_bid:
            text_lines.append(f"💰 Ваша ставка: {last_bid.amount:,.2f} ₽")
        text_lines.append(f"📊 Текущая цена: {lot.current_price:,.2f} ₽")
        text_lines.append(f"📅 Статус: {info['status']}")
        text_lines.append(
            f"🕐 Окончание: {lot.end_time.strftime('%d.%m.%Y %H:%M') if lot.end_time else 'Не определено'}\n"
        )

    text_lines.append(f"Показано {start + 1}-{min(end, total_items)} из {total_items}")
    text = "\n".join(text_lines)

    buttons = []
    for info in page_items:
        lot = info["lot"]
        title = lot.title if len(lot.title) <= 24 else lot.title[:21] + "..."
        buttons.append(
            [InlineKeyboardButton(text=f"📦 {title}", callback_data=f"my_lot:{lot.id}")]
        )

    # Строка пагинации
    prev_page = page - 1 if page > 1 else 1
    next_page = page + 1 if page < total_pages else total_pages
    pagination_row = [
        InlineKeyboardButton(
            text="◀️", callback_data=f"my_participation_page:{prev_page}"
        ),
        InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
        InlineKeyboardButton(
            text="▶️", callback_data=f"my_participation_page:{next_page}"
        ),
    ]
    buttons.append(pagination_row)

    # Кнопка назад
    buttons.append(
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")]
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return text, keyboard


async def show_my_participation_message(message: Message):
    """Показывает 'Мое участие' по сообщению (из главного меню), страница 1"""
    # Проверяем блокировку
    if await check_user_banned(message):
        return

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            await message.answer("❌ Пользователь не найден")
            return

        text, keyboard = _build_my_participation_page(db, user, page=1, per_page=5)
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка при показе 'Мое участие' (message): {e}")
        await message.answer("❌ Ошибка при получении данных")
    finally:
        db.close()


@router.callback_query(F.data.startswith("my_participation_page:"))
async def paginate_my_participation(callback: CallbackQuery):
    """Обработчик пагинации раздела 'Мое участие'"""
    # Проверяем блокировку
    if await check_user_banned_callback(callback):
        return

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return

        try:
            page = int(callback.data.split(":")[1])
        except Exception:
            page = 1

        text, keyboard = _build_my_participation_page(db, user, page=page, per_page=5)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка пагинации 'Мое участие': {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
    finally:
        db.close()


@router.callback_query(F.data == "noop")
async def ignore_noop(callback: CallbackQuery):
    """Не делает ничего для неактивных кнопок"""
    try:
        await callback.answer()
    except Exception:
        pass


@router.callback_query(F.data == "cancel")
async def cancel_action(callback: CallbackQuery, state: FSMContext):
    """Отмена текущего действия"""
    try:
        await state.clear()
        await callback.answer("❌ Действие отменено")
        await callback.message.edit_text(
            "🎉 Добро пожаловать в аукционный бот!\n\n"
            "Используйте кнопки ниже для навигации:",
            reply_markup=get_main_keyboard(),
        )
    except Exception as e:
        logger.error(f"Ошибка при отмене действия: {e}")
        await callback.answer("❌ Ошибка")


@router.callback_query(F.data == "back_to_main")
async def back_to_main_menu(callback: CallbackQuery):
    """Возврат в главное меню"""
    try:
        await callback.message.edit_text(
            "🎉 Добро пожаловать в аукционный бот!\n\n"
            "Здесь вы можете:\n"
            "• Участвовать в аукционах\n"
            "• Создавать свои лоты\n"
            "• Делать ставки\n"
            "• Отслеживать активные торги\n\n"
            "Используйте кнопки ниже для навигации:",
            reply_markup=get_main_keyboard(),
        )
        await callback.answer()
    except Exception as e:
        # Если не удалось отредактировать, возможно сообщение с изображением
        if "there is no text in the message to edit" in str(e).lower():
            try:
                await callback.message.edit_caption(
                    caption="🎉 Добро пожаловать в аукционный бот!\n\n"
                    "Здесь вы можете:\n"
                    "• Участвовать в аукционах\n"
                    "• Создавать свои лоты\n"
                    "• Делать ставки\n"
                    "• Отслеживать активные торги\n\n"
                    "Используйте кнопки ниже для навигации:",
                    reply_markup=get_main_keyboard(),
                )
                await callback.answer()
            except Exception:
                # В крайнем случае отправляем новое сообщение
                await callback.message.answer(
                    "🎉 Добро пожаловать в аукционный бот!\n\n"
                    "Здесь вы можете:\n"
                    "• Участвовать в аукционах\n"
                    "• Создавать свои лоты\n"
                    "• Делать ставки\n"
                    "• Отслеживать активные торги\n\n"
                    "Используйте кнопки ниже для навигации:",
                    reply_markup=get_main_keyboard(),
                )
        else:
            logger.error(f"Ошибка при возврате в главное меню: {e}")
            await callback.answer("❌ Ошибка")


@router.callback_query(F.data.startswith("my_lot:"))
async def show_my_lot_details(callback: CallbackQuery):
    """Показать детали лота пользователя"""
    # Проверяем блокировку
    if await check_user_banned_callback(callback):
        return

    lot_id = int(callback.data.split(":")[1])
    db = SessionLocal()

    try:
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        lot = db.query(Lot).filter(Lot.id == lot_id).first()

        if not lot:
            await callback.answer("❌ Лот не найден")
            return

        # Получаем ставки пользователя на этот лот
        user_bids = (
            db.query(Bid)
            .filter(Bid.lot_id == lot_id, Bid.bidder_id == user.id)
            .order_by(Bid.created_at.desc())
            .all()
        )

        # Получаем последнюю ставку пользователя
        last_user_bid = user_bids[0] if user_bids else None

        # Получаем максимальную ставку на лот
        max_bid = (
            db.query(Bid)
            .filter(Bid.lot_id == lot_id)
            .order_by(Bid.amount.desc())
            .first()
        )

        # Определяем статус
        if lot.status == LotStatus.SOLD:
            if max_bid and max_bid.bidder_id == user.id:
                status = "🏆 Вы выиграли этот лот!"
                status_emoji = "🏆"
            else:
                status = "💸 Вы не выиграли этот лот"
                status_emoji = "💸"
        elif (
            lot.status == LotStatus.ACTIVE
            and lot.end_time > get_moscow_time().replace(tzinfo=None)
        ):
            if max_bid and max_bid.bidder_id == user.id:
                status = "🥇 Вы лидируете!"
                status_emoji = "🥇"
            else:
                status = "🔄 Аукцион активен"
                status_emoji = "🔄"
        else:
            status = "⏰ Аукцион завершен"
            status_emoji = "⏰"

        # Формируем информацию о ставках
        last_bid_text = (
            f"{last_user_bid.amount:,.2f} ₽" if last_user_bid else "Нет ставок"
        )
        max_bid_text = f"{max_bid.amount:,.2f} ₽" if max_bid else "Нет ставок"

        text = f"""
{status_emoji} **{lot.title}**

📝 **Описание:** {lot.description or 'Описание отсутствует'}

💰 **Цены:**
• Текущая цена: {lot.current_price:,.2f} ₽
• Ваша последняя ставка: {last_bid_text}
• Максимальная ставка: {max_bid_text}

📊 **Статистика:**
• Всего ставок: {len(lot.bids)}
• Ваших ставок: {len(user_bids)}
• Статус: {status}

⏰ **Время:**
• Окончание: {lot.end_time.strftime('%d.%m.%Y %H:%M')}
• Создан: {lot.created_at.strftime('%d.%m.%Y %H:%M')}
        """

        # Создаем клавиатуру
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard_buttons = []

        if lot.status == LotStatus.ACTIVE and lot.end_time > get_moscow_time().replace(
            tzinfo=None
        ):
            keyboard_buttons.append(
                [
                    InlineKeyboardButton(
                        text="💰 Сделать ставку", callback_data=f"bid:{lot_id}"
                    )
                ]
            )

        keyboard_buttons.append(
            [
                InlineKeyboardButton(
                    text="📋 История ставок", callback_data=f"bid_history:{lot_id}"
                )
            ]
        )

        keyboard_buttons.append(
            [
                InlineKeyboardButton(
                    text="🔙 Назад к участию", callback_data="my_participation"
                )
            ]
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Ошибка при получении деталей лота: {e}")
        await callback.answer("❌ Ошибка при получении данных")
    finally:
        db.close()


@router.callback_query(F.data == "user_stats")
async def show_user_stats(callback: CallbackQuery):
    """Показывает статистику пользователя"""
    # Проверяем блокировку
    if await check_user_banned_callback(callback):
        return

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()

        # Подсчитываем статистику
        total_bids = db.query(Bid).filter(Bid.bidder_id == user.id).count()
        won_auctions = (
            db.query(Bid).filter(Bid.bidder_id == user.id).distinct(Bid.lot_id).count()
        )

        total_spent = (
            db.query(Payment)
            .filter(Payment.user_id == user.id, Payment.status == "completed")
            .with_entities(func.sum(Payment.amount))
            .scalar()
            or 0
        )

        text = f"""
📊 **Статистика пользователя**

**Ставки:**
💰 Всего ставок: {total_bids}
🏆 Выигранных аукционов: {won_auctions}

**Покупки:**
💳 Успешных покупок: {user.successful_payments}
💸 Общая сумма покупок: {total_spent:,.2f} ₽

**Активность:**
📅 Дата регистрации: {user.created_at.strftime('%d.%m.%Y')}
⚠️ Страйков: {user.strikes}/3
        """

        await callback.message.edit_text(text)

    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        await callback.answer("❌ Ошибка при получении статистики")
    finally:
        db.close()


@router.callback_query(F.data == "back_to_profile")
async def back_to_profile(callback: CallbackQuery):
    """Возврат к профилю"""
    # Проверяем блокировку
    if await check_user_banned_callback(callback):
        return

    try:
        await callback.message.edit_text(
            "👤 **Личный кабинет**\n\n" "Выберите действие:",
            reply_markup=get_user_profile_keyboard(),
            parse_mode="Markdown",
        )
        await callback.answer()
    except Exception as e:
        # Если не удалось отредактировать, возможно сообщение с изображением
        if "there is no text in the message to edit" in str(e).lower():
            try:
                await callback.message.edit_caption(
                    caption="👤 **Личный кабинет**\n\n" "Выберите действие:",
                    reply_markup=get_user_profile_keyboard(),
                    parse_mode="Markdown",
                )
                await callback.answer()
            except Exception:
                # В крайнем случае отправляем новое сообщение
                await callback.message.answer(
                    "👤 **Личный кабинет**\n\n" "Выберите действие:",
                    reply_markup=get_user_profile_keyboard(),
                    parse_mode="Markdown",
                )
        else:
            logger.error(f"Ошибка при возврате к профилю: {e}")
            await callback.answer("❌ Ошибка")


@router.message(Command("balance"))
async def show_balance(message: Message):
    """Показать баланс пользователя"""
    # Проверяем блокировку
    if await check_user_banned(message):
        return

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if user:
            await message.answer(f"💰 **Ваш баланс:** {user.balance:,.2f} ₽")
        else:
            await message.answer("❌ Пользователь не найден")
    except Exception as e:
        logger.error(f"Ошибка при получении баланса: {e}")
        await message.answer("❌ Ошибка при получении баланса")
    finally:
        db.close()


@router.message(F.text == "👤 Личный кабинет")
async def show_profile_from_menu(message: Message):
    """Показать профиль из главного меню"""
    await user_profile(message)


# Удаляем дублирующийся обработчик - основной обработчик уже есть выше


@router.message(F.text == "🎯 Мое участие")
async def show_my_participation_from_menu(message: Message):
    """Показать участие пользователя из главного меню"""
    # Проверяем блокировку
    if await check_user_banned(message):
        return

    await show_my_participation_message(message)


@router.message(F.text == "💰 Мои ставки")
async def show_my_bids_from_menu(message: Message, state: FSMContext):
    """Показать мои ставки из главного меню"""
    # Проверяем блокировку
    if await check_user_banned(message):
        return

    # Импорт функции из bids.py
    from bot.handlers.bids import my_bids

    await my_bids(message, state)


@router.message(F.text == "📋 История торгов")
async def show_trading_history(message: Message):
    """Показать историю торгов"""
    # Проверяем блокировку
    if await check_user_banned(message):
        return

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            await message.answer("❌ Пользователь не найден")
            return

        # Получаем последние ставки пользователя
        recent_bids = (
            db.query(Bid)
            .filter(Bid.bidder_id == user.id)
            .order_by(Bid.created_at.desc())
            .limit(10)
            .all()
        )

        if not recent_bids:
            await message.answer("📋 У вас пока нет истории торгов")
            return

        text = "📋 **Ваша история торгов:**\n\n"
        for bid in recent_bids:
            lot = db.query(Lot).filter(Lot.id == bid.lot_id).first()
            if lot:
                text += f"🏷️ **{lot.title}**\n"
                text += f"💰 Ставка: {bid.amount:,.2f} ₽\n"
                text += f"📅 Дата: {bid.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                text += f"🤖 Автоставка: {'Да' if bid.is_auto_bid else 'Нет'}\n\n"

        await message.answer(text, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Ошибка при получении истории торгов: {e}")
        await message.answer("❌ Ошибка при получении истории торгов")
    finally:
        db.close()


@router.message(F.text == "📞 Поддержка")
async def show_support_from_menu(message: Message):
    """Показать поддержку из главного меню"""
    # Проверяем блокировку
    if await check_user_banned(message):
        return

    await message.answer(
        "📞 **Поддержка**\n\n"
        "Если у вас есть вопросы или проблемы:\n\n"
        "1️⃣ Напишите ваш вопрос\n"
        "2️⃣ Опишите проблему подробно\n"
        "3️⃣ Приложите скриншоты, если нужно\n\n"
        "Наши специалисты ответят вам в ближайшее время.",
        reply_markup=get_main_keyboard(),
    )


@router.message(F.text == "⚙️ Настройки")
async def show_settings(message: Message):
    """Показать настройки"""
    # Проверяем блокировку
    if await check_user_banned(message):
        return

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

        text = f"""
⚙️ **Настройки**

🤖 **Автоставки:** {'✅ Включены' if user.auto_bid_enabled else '❌ Отключены'}

📊 **Условия для автоставок:**
• Минимум успешных покупок: {AUTO_BID_MIN_PAYMENTS}
• Ваш прогресс: {user.successful_payments}/{AUTO_BID_MIN_PAYMENTS}

🔔 **Уведомления:** {'Включены' if user.notifications_enabled else 'Отключены'}

📱 **Язык:** Русский

💡 Для изменения настроек используйте кнопки ниже.
        """

        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🤖 Настройки автоставок",
                        callback_data="auto_bid_settings",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=(
                            "Включить уведомления"
                            if not user.notifications_enabled
                            else "Отключить уведомления"
                        ),
                        callback_data=(
                            "enable_notifications"
                            if not user.notifications_enabled
                            else "disable_notifications"
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔙 Назад", callback_data="back_to_profile"
                    )
                ],
            ]
        )

        await message.answer(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Ошибка при получении настроек: {e}")
        await message.answer("❌ Ошибка при получении настроек")
    finally:
        db.close()


@router.callback_query(F.data.startswith("auto_bid:"))
async def handle_auto_bid(callback: CallbackQuery, state: FSMContext):
    """Обработчик автоставки - запрашивает максимальную сумму"""
    db = SessionLocal()
    try:
        lot_id = int(callback.data.split(":")[1])
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        lot = db.query(Lot).filter(Lot.id == lot_id).first()
        allow_auto_bid_for_test_user(user, db)
        # Запретить автоставку для продавца на свой лот
        if lot and user and lot.seller_id == user.id:
            await callback.answer(
                "❌ Вы не можете использовать автоставку на свой собственный лот"
            )
            return

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

        # Проверяем доступ к автоставкам: если ранее включены и задан лимит, переиспользуем и не просим ввод
        if not user.auto_bid_enabled:
            await callback.answer("❌ Автоставки недоступны")
            return

        if user.successful_payments < AUTO_BID_MIN_PAYMENTS:
            await callback.answer(
                f"❌ Требуется {AUTO_BID_MIN_PAYMENTS}+ успешных покупок"
            )
            return

        # Если max_bid_amount уже задан, позволяем пользователю его изменить (не блокируем повторный ввод)
        # Просто продолжаем к запросу нового значения

        # Сохраняем данные в состоянии
        await state.update_data(lot_id=lot_id, message_id=callback.message.message_id)
        await state.set_state(BidStates.waiting_for_max_bid_amount)

        # Рассчитываем минимальную ставку
        from bot.utils.bid_calculator import calculate_min_bid

        min_bid = calculate_min_bid(lot.current_price)

        # Создаем текст сообщения
        text = (
            f"🤖 <b>Настройка автоставки</b>\n\n"
            f"🏷️ <b>Лот:</b> {lot.title}\n"
            f"💰 <b>Текущая цена:</b> {lot.current_price:,.2f} ₽\n"
            f"📈 <b>Минимальная ставка:</b> {min_bid:,.2f} ₽\n\n"
            f"💰 <b>Введите максимальную сумму автоставки</b>\n"
            f"ℹ️ Автоставка будет автоматически повышать вашу ставку до этой суммы\n"
            f"❌ Не используйте символы ₽, запятые или пробелы"
        )

        # Создаем клавиатуру с кнопкой "Назад"
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔙 Назад к лоту",
                        callback_data=f"lot_details:{lot_id}",
                    )
                ]
            ]
        )

        # Редактируем текущее сообщение
        await _safe_edit_text(callback.message, text, reply_markup=keyboard)
        await _safe_callback_answer(callback, "🤖 Введите максимальную сумму")

    except Exception as e:
        logger.error(f"Ошибка при настройке автоставки: {e}")
        await _safe_callback_answer(callback, "❌ Произошла ошибка")
    finally:
        db.close()


@router.callback_query(F.data.startswith("enable_auto_bid"))
async def enable_auto_bid(callback: CallbackQuery):
    """Включить автоставки"""
    # Проверяем блокировку
    if await check_user_banned_callback(callback):
        return

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        allow_auto_bid_for_test_user(user, db)

        if user.successful_payments < AUTO_BID_MIN_PAYMENTS:
            await callback.answer(
                f"❌ Требуется {AUTO_BID_MIN_PAYMENTS}+ успешных покупок"
            )
            return

        user.auto_bid_enabled = True
        db.commit()
        await callback.answer("🤖 Автоставки включены")

        # Обновляем экран настроек автоставок
        text, keyboard = get_auto_bid_settings_text_and_keyboard(user)
        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Ошибка при включении автоставок: {e}")
        await callback.answer("❌ Ошибка при включении автоставок")
    finally:
        db.close()


@router.callback_query(F.data.startswith("disable_auto_bid"))
async def disable_auto_bid(callback: CallbackQuery):
    """Отключить автоставки"""
    # Проверяем блокировку
    if await check_user_banned_callback(callback):
        return

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()

        user.auto_bid_enabled = False
        user.max_bid_amount = None  # Сбрасываем максимальную сумму
        db.commit()
        await callback.answer("🤖 Автоставки отключены")

        # Обновляем экран настроек автоставок
        text, keyboard = get_auto_bid_settings_text_and_keyboard(user)
        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Ошибка при отключении автоставок: {e}")
        await callback.answer("❌ Ошибка при отключении автоставок")
    finally:
        db.close()


@router.callback_query(F.data.startswith("bid_history:"))
async def show_bid_history(callback: CallbackQuery):
    """Показать историю ставок на конкретный лот"""
    # Проверяем блокировку
    if await check_user_banned_callback(callback):
        return

    lot_id = int(callback.data.split(":")[1])
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        lot = db.query(Lot).filter(Lot.id == lot_id).first()

        if not lot:
            await callback.answer("❌ Лот не найден")
            return

        # Получаем все ставки пользователя на этот лот
        user_bids = (
            db.query(Bid)
            .filter(Bid.lot_id == lot_id, Bid.bidder_id == user.id)
            .order_by(Bid.created_at.desc())
            .all()
        )

        if not user_bids:
            await callback.answer("❌ У вас нет ставок на этот лот")
            return

        text = f"📋 **История ваших ставок на лот:** {lot.title}\n\n"

        for i, bid in enumerate(user_bids, 1):
            text += f"{i}. {bid.amount:,.2f} ₽ - {bid.created_at.strftime('%d.%m.%Y %H:%M')}\n"

        await callback.message.edit_text(text)

    except Exception as e:
        logger.error(f"Ошибка при получении истории ставок: {e}")
        await callback.answer("❌ Ошибка при получении истории")
    finally:
        db.close()


@router.callback_query(F.data.startswith("disable_auto_bid_for_lot:"))
async def disable_auto_bid_for_lot(callback: CallbackQuery):
    """Отключить автоставку для конкретного лота"""
    # Проверяем блокировку
    if await check_user_banned_callback(callback):
        return

    db = SessionLocal()
    try:
        lot_id = int(callback.data.split(":")[1])
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()

        if not user:
            await callback.answer("❌ Пользователь не найден")
            return

        # Получаем лот для обновления клавиатуры
        lot = db.query(Lot).filter(Lot.id == lot_id).first()
        if not lot:
            await callback.answer("❌ Лот не найден")
            return

        # Отключаем автоставку для лота
        from bot.utils.auto_bid_manager import AutoBidManager

        success = AutoBidManager.disable_auto_bid_for_lot(user.id, lot_id)

        if success:
            await callback.answer("✅ Автоставка отключена для этого лота")

            # Обновляем клавиатуру, убирая кнопку отключения автоставки
            # Создаем новый текст сообщения
            from bot.utils.bid_calculator import format_bid_info
            from bot.utils.keyboards import get_bid_keyboard

            bid_info = format_bid_info(lot.current_price)
            bid_text = (
                f"💰 <b>Сделать ставку</b>\n\n"
                f"🏷️ <b>Лот:</b> {lot.title}\n\n"
                f"{bid_info}"
            )

            # Создаем клавиатуру без кнопки отключения автоставки
            bid_keyboard = get_bid_keyboard(lot.id, lot.current_price, user.id)

            # Редактируем сообщение с обновленной клавиатурой
            try:
                await callback.message.edit_text(
                    bid_text, reply_markup=bid_keyboard, parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Ошибка при обновлении клавиатуры: {e}")
                # Если не удалось отредактировать, отправляем новое сообщение
                await callback.message.answer(
                    bid_text, reply_markup=bid_keyboard, parse_mode="HTML"
                )
        else:
            await callback.answer("❌ Ошибка при отключении автоставки")

    except Exception as e:
        logger.error(f"Ошибка при отключении автоставки для лота: {e}")
        await callback.answer("❌ Произошла ошибка")
    finally:
        db.close()


@router.callback_query(F.data == "back_to_settings")
async def back_to_settings(callback: CallbackQuery):
    """Возврат в настройки"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not user:
            await callback.answer("❌ Пользователь не найден")
            return

        text = f"""
⚙️ **Настройки**

🤖 **Автоставки:** {'✅ Включены' if user.auto_bid_enabled else '❌ Отключены'}

📊 **Условия для автоставок:**
• Минимум успешных покупок: {AUTO_BID_MIN_PAYMENTS}
• Ваш прогресс: {user.successful_payments}/{AUTO_BID_MIN_PAYMENTS}

🔔 **Уведомления:** {'Включены' if user.notifications_enabled else 'Отключены'}

📱 **Язык:** Русский

💡 Для изменения настроек используйте кнопки ниже.
        """

        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🤖 Настройки автоставок",
                        callback_data="auto_bid_settings",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=(
                            "Включить уведомления"
                            if not user.notifications_enabled
                            else "Отключить уведомления"
                        ),
                        callback_data=(
                            "enable_notifications"
                            if not user.notifications_enabled
                            else "disable_notifications"
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔙 Назад", callback_data="back_to_profile"
                    )
                ],
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Ошибка при возврате в настройки: {e}")
        await callback.answer("❌ Ошибка при получении настроек")
    finally:
        db.close()


@router.callback_query(F.data == "enable_notifications")
async def enable_notifications(callback: CallbackQuery):
    # Проверяем блокировку
    if await check_user_banned_callback(callback):
        return

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not user:
            await callback.answer("❌ Пользователь не найден")
            return
        user.notifications_enabled = True
        db.commit()
        await callback.answer("🔔 Уведомления включены")

        # Обновляем сообщение с новыми настройками
        text = f"""
⚙️ **Настройки**

🤖 **Автоставки:** {'✅ Включены' if user.auto_bid_enabled else '❌ Отключены'}

📊 **Условия для автоставок:**
• Минимум успешных покупок: {AUTO_BID_MIN_PAYMENTS}
• Ваш прогресс: {user.successful_payments}/{AUTO_BID_MIN_PAYMENTS}

🔔 **Уведомления:** {'Включены' if user.notifications_enabled else 'Отключены'}

📱 **Язык:** Русский

💡 Для изменения настроек используйте кнопки ниже.
        """

        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🤖 Настройки автоставок",
                        callback_data="auto_bid_settings",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=(
                            "Включить уведомления"
                            if not user.notifications_enabled
                            else "Отключить уведомления"
                        ),
                        callback_data=(
                            "enable_notifications"
                            if not user.notifications_enabled
                            else "disable_notifications"
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔙 Назад", callback_data="back_to_profile"
                    )
                ],
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Ошибка при включении уведомлений: {e}")
        await callback.answer("❌ Ошибка при включении уведомлений")
    finally:
        db.close()


@router.callback_query(F.data == "disable_notifications")
async def disable_notifications(callback: CallbackQuery):
    # Проверяем блокировку
    if await check_user_banned_callback(callback):
        return

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not user:
            await callback.answer("❌ Пользователь не найден")
            return
        user.notifications_enabled = False
        db.commit()
        await callback.answer("🔕 Уведомления отключены")

        # Обновляем сообщение с новыми настройками
        text = f"""
⚙️ **Настройки**

🤖 **Автоставки:** {'✅ Включены' if user.auto_bid_enabled else '❌ Отключены'}

📊 **Условия для автоставок:**
• Минимум успешных покупок: {AUTO_BID_MIN_PAYMENTS}
• Ваш прогресс: {user.successful_payments}/{AUTO_BID_MIN_PAYMENTS}

🔔 **Уведомления:** {'Включены' if user.notifications_enabled else 'Отключены'}

📱 **Язык:** Русский

💡 Для изменения настроек используйте кнопки ниже.
        """

        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🤖 Настройки автоставок",
                        callback_data="auto_bid_settings",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=(
                            "Включить уведомления"
                            if not user.notifications_enabled
                            else "Отключить уведомления"
                        ),
                        callback_data=(
                            "enable_notifications"
                            if not user.notifications_enabled
                            else "disable_notifications"
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔙 Назад", callback_data="back_to_profile"
                    )
                ],
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Ошибка при отключении уведомлений: {e}")
        await callback.answer("❌ Ошибка при отключении уведомлений")
    finally:
        db.close()


@router.message(Command("test_ban"))
async def test_ban_status(message: Message):
    """Тестовая команда для проверки статуса блокировки"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if user:
            status = "заблокирован" if user.is_banned else "не заблокирован"
            await message.answer(
                f"🔍 **Тест статуса блокировки**\n\n"
                f"👤 Пользователь: {user.first_name}\n"
                f"🆔 Telegram ID: {user.telegram_id}\n"
                f"⚠️ Страйки: {user.strikes}/3\n"
                f"🚫 Статус: {status}\n"
                f"📅 Регистрация: {user.created_at.strftime('%d.%m.%Y %H:%M')}"
            )
        else:
            await message.answer("❌ Пользователь не найден в базе данных")
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса блокировки: {e}")
        await message.answer("❌ Ошибка при проверке статуса")
    finally:
        db.close()


@router.message(Command("debug_ban"))
async def debug_ban_user(message: Message):
    """Отладочная команда для блокировки/разблокировки пользователя"""
    # Проверяем, является ли пользователь супер-админом
    if message.from_user.id not in SUPER_ADMIN_IDS:
        await message.answer("❌ Эта команда доступна только супер-администраторам")
        return

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if user:
            # Переключаем статус блокировки
            user.is_banned = not user.is_banned
            db.commit()

            status = "заблокирован" if user.is_banned else "разблокирован"
            await message.answer(
                f"🔧 **Отладка блокировки**\n\n"
                f"👤 Пользователь: {user.first_name}\n"
                f"🆔 Telegram ID: {user.telegram_id}\n"
                f"🚫 Статус: {status}\n"
                f"⚠️ Страйки: {user.strikes}/3\n\n"
                f"Теперь попробуйте нажать '🎯 Мое участие'"
            )
        else:
            await message.answer("❌ Пользователь не найден в базе данных")
    except Exception as e:
        logger.error(f"Ошибка при отладке блокировки: {e}")
        await message.answer("❌ Ошибка при изменении статуса")
    finally:
        db.close()


@router.message(Command("debug_check"))
async def debug_check_user(message: Message):
    """Отладочная команда для проверки пользователя в базе данных"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if user:
            await message.answer(
                f"🔍 **Проверка пользователя**\n\n"
                f"👤 Имя: {user.first_name}\n"
                f"🆔 Telegram ID: {user.telegram_id}\n"
                f"🆔 User ID: {user.id}\n"
                f"🚫 is_banned: {user.is_banned}\n"
                f"⚠️ Страйки: {user.strikes}/3\n"
                f"📅 Регистрация: {user.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                f"Попробуйте команду /debug_ban для переключения блокировки"
            )
        else:
            await message.answer("❌ Пользователь не найден в базе данных")
    except Exception as e:
        logger.error(f"Ошибка при проверке пользователя: {e}")
        await message.answer("❌ Ошибка при проверке")
    finally:
        db.close()
