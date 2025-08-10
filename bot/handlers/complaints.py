import logging
from datetime import datetime
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.orm import Session

from bot.utils.keyboards import get_complaint_keyboard
from config.settings import SUPER_ADMIN_IDS, SUPPORT_IDS
from database.db import SessionLocal
from database.models import Complaint, Lot, User, UserRole

router = Router()
logger = logging.getLogger(__name__)


class ComplaintStates(StatesGroup):
    """Состояния для подачи жалобы"""

    waiting_for_target = State()
    waiting_for_reason = State()
    waiting_for_evidence = State()


@router.message(Command("complaint"))
async def complaint_menu(message: Message):
    """Меню жалоб"""
    await message.answer(
        "📝 <b>Система жалоб</b>\n\n"
        "Здесь вы можете подать жалобу на недобросовестного администратора "
        "или другого участника аукциона.\n\n"
        "Выберите действие:",
        reply_markup=get_complaint_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "submit_complaint")
async def start_complaint(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс подачи жалобы"""
    await callback.answer()

    await callback.message.answer(
        "📝 <b>Подача жалобы</b>\n\n"
        "Укажите username пользователя (без @), на которого подаете жалобу.\n"
        "Например: username123",
        parse_mode="HTML",
    )

    await state.set_state(ComplaintStates.waiting_for_target)


@router.message(ComplaintStates.waiting_for_target)
async def process_complaint_target(message: Message, state: FSMContext):
    """Обрабатывает указание цели жалобы"""
    username = message.text.strip()

    # Убираем @ если пользователь его добавил
    if username.startswith("@"):
        username = username[1:]

    if not username or len(username) < 3:
        await message.answer(
            "❌ Неверный формат username.\n"
            "Введите username пользователя (например: username123)"
        )
        return

    db = SessionLocal()
    try:
        target_user = db.query(User).filter(User.username == username).first()
        if not target_user:
            await message.answer(
                "❌ Пользователь с таким username не найден в системе.\n"
                "Проверьте username и попробуйте снова."
            )
            return

        # Сохраняем ID цели
        await state.update_data(target_user_id=target_user.id)

        await message.answer(
            f"✅ Цель жалобы: @{target_user.username} ({target_user.first_name})\n\n"
            "Теперь опишите причину жалобы:",
            parse_mode="HTML",
        )

        await state.set_state(ComplaintStates.waiting_for_reason)

    except Exception as e:
        logger.error(f"Ошибка при поиске пользователя: {e}")
        await message.answer("❌ Ошибка при поиске пользователя. Попробуйте позже.")
    finally:
        db.close()


@router.message(ComplaintStates.waiting_for_reason)
async def process_complaint_reason(message: Message, state: FSMContext):
    """Обрабатывает причину жалобы"""
    reason = message.text.strip()

    if len(reason) < 10:
        await message.answer(
            "❌ Описание жалобы должно содержать минимум 10 символов.\n"
            "Пожалуйста, опишите проблему подробнее."
        )
        return

    # Сохраняем причину
    await state.update_data(reason=reason)

    await message.answer(
        "📝 <b>Дополнительные доказательства</b>\n\n"
        "Если у вас есть дополнительные доказательства (скриншоты, ссылки), "
        "отправьте их сейчас.\n\n"
        "Или отправьте 'нет' для пропуска этого шага.",
        parse_mode="HTML",
    )

    await state.set_state(ComplaintStates.waiting_for_evidence)


@router.message(ComplaintStates.waiting_for_evidence)
async def process_complaint_evidence(message: Message, state: FSMContext):
    """Обрабатывает доказательства жалобы"""
    evidence = message.text.strip()

    if evidence.lower() in ["нет", "no", "пропустить", "skip"]:
        evidence = None

    # Получаем данные из состояния
    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    reason = data.get("reason")

    if not target_user_id or not reason:
        await message.answer("❌ Ошибка при создании жалобы. Попробуйте снова.")
        await state.clear()
        return

    # Создаем жалобу
    db = SessionLocal()
    try:
        complainant = (
            db.query(User).filter(User.telegram_id == message.from_user.id).first()
        )
        if not complainant:
            await message.answer("❌ Ошибка: пользователь не найден.")
            await state.clear()
            return

        complaint = Complaint(
            complainant_id=complainant.id,
            target_user_id=target_user_id,
            reason=reason,
            evidence=evidence,
            status="pending",
        )

        db.add(complaint)
        db.commit()

        await message.answer(
            "✅ <b>Жалоба успешно подана!</b>\n\n"
            f"📝 <b>Номер жалобы:</b> #{complaint.id}\n"
            f"📅 <b>Дата подачи:</b> {complaint.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            "Ваша жалоба будет рассмотрена службой поддержки в ближайшее время.",
            parse_mode="HTML",
        )

        # Уведомляем службу поддержки
        await notify_support_about_complaint(complaint, complainant)

    except Exception as e:
        logger.error(f"Ошибка при создании жалобы: {e}")
        await message.answer("❌ Ошибка при создании жалобы. Попробуйте позже.")
    finally:
        db.close()


@router.callback_query(F.data == "my_complaints")
async def show_my_complaints(callback: CallbackQuery):
    """Показывает жалобы пользователя"""
    await callback.answer()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not user:
            await callback.message.answer("❌ Пользователь не найден.")
            return

        complaints = (
            db.query(Complaint).filter(Complaint.complainant_id == user.id).all()
        )

        if not complaints:
            await callback.message.answer(
                "📝 <b>Мои жалобы</b>\n\n" "У вас пока нет поданных жалоб.",
                parse_mode="HTML",
            )
            return

        text = "📝 <b>Мои жалобы</b>\n\n"

        for complaint in complaints[:10]:  # Показываем последние 10
            target_user = (
                db.query(User).filter(User.id == complaint.target_user_id).first()
            )
            target_name = target_user.first_name if target_user else "Неизвестно"

            status_emoji = {"pending": "⏳", "reviewed": "👁️", "resolved": "✅"}.get(
                complaint.status, "❓"
            )

            text += f"{status_emoji} <b>Жалоба #{complaint.id}</b>\n"
            text += f"👤 На: {target_name}\n"
            text += f"📅 {complaint.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            text += f"📝 {complaint.reason[:50]}{'...' if len(complaint.reason) > 50 else ''}\n\n"

        if len(complaints) > 10:
            text += f"... и еще {len(complaints) - 10} жалоб"

        await callback.message.answer(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка при получении жалоб: {e}")
        await callback.message.answer("❌ Ошибка при получении жалоб.")
    finally:
        db.close()


async def notify_support_about_complaint(complaint: Complaint, complainant: User):
    """Уведомляет службу поддержки о новой жалобе"""
    try:
        from aiogram import Bot

        from config.settings import BOT_TOKEN

        bot = Bot(token=BOT_TOKEN)

        support_message = f"""
🚨 <b>НОВАЯ ЖАЛОБА</b>

📝 <b>Жалоба #{complaint.id}</b>
👤 <b>От:</b> {complainant.first_name} (@{complainant.username or 'N/A'})
👤 <b>На:</b> Пользователь #{complaint.target_user_id}
📅 <b>Дата:</b> {complaint.created_at.strftime('%d.%m.%Y %H:%M')}

📝 <b>Причина:</b>
{complaint.reason}

{f'📎 <b>Доказательства:</b>\n{complaint.evidence}' if complaint.evidence else ''}

🔗 <b>Действия:</b>
• /review_complaint_{complaint.id} - Рассмотреть жалобу
• /resolve_complaint_{complaint.id} - Разрешить жалобу
        """.strip()

        # Отправляем уведомление всем службам поддержки
        for support_id in SUPPORT_IDS + SUPER_ADMIN_IDS:
            try:
                await bot.send_message(
                    chat_id=support_id, text=support_message, parse_mode="HTML"
                )
            except Exception as e:
                logger.error(
                    f"Ошибка при отправке уведомления поддержке {support_id}: {e}"
                )

        await bot.session.close()

    except Exception as e:
        logger.error(f"Ошибка при уведомлении поддержки: {e}")


@router.message(Command("review_complaint"))
async def review_complaint_command(message: Message):
    """Команда для рассмотрения жалобы (только для поддержки)"""
    if message.from_user.id not in SUPPORT_IDS + SUPER_ADMIN_IDS:
        await message.answer("❌ У вас нет прав для рассмотрения жалоб.")
        return

    # Парсим ID жалобы из команды
    command_parts = message.text.split()
    if len(command_parts) < 2:
        await message.answer("❌ Укажите ID жалобы: /review_complaint <ID>")
        return

    try:
        complaint_id = int(command_parts[1])
        await show_complaint_details(message, complaint_id)
    except ValueError:
        await message.answer("❌ Неверный ID жалобы.")


async def show_complaint_details(message: Message, complaint_id: int):
    """Показывает детали жалобы для рассмотрения"""
    db = SessionLocal()
    try:
        complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
        if not complaint:
            await message.answer("❌ Жалоба не найдена.")
            return

        complainant = db.query(User).filter(User.id == complaint.complainant_id).first()
        target_user = db.query(User).filter(User.id == complaint.target_user_id).first()

        text = f"""
📝 <b>ЖАЛОБА #{complaint.id}</b>

👤 <b>От:</b> {complainant.first_name} (@{complainant.username or 'N/A'})
👤 <b>На:</b> {target_user.first_name} (@{target_user.username or 'N/A'})
📅 <b>Дата:</b> {complaint.created_at.strftime('%d.%m.%Y %H:%M')}
📊 <b>Статус:</b> {complaint.status}

📝 <b>Причина:</b>
{complaint.reason}

{f'📎 <b>Доказательства:</b>\n{complaint.evidence}' if complaint.evidence else ''}

{f'✅ <b>Решение:</b>\n{complaint.resolution}' if complaint.resolution else ''}
        """.strip()

        # Создаем клавиатуру для действий
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Разрешить",
                        callback_data=f"resolve_complaint:{complaint_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отклонить",
                        callback_data=f"reject_complaint:{complaint_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⚠️ Выдать страйк",
                        callback_data=f"strike_user:{complaint.target_user_id}",
                    )
                ],
            ]
        )

        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка при получении деталей жалобы: {e}")
        await message.answer("❌ Ошибка при получении деталей жалобы.")
    finally:
        db.close()


@router.callback_query(F.data.startswith("resolve_complaint:"))
async def resolve_complaint(callback: CallbackQuery):
    """Разрешает жалобу"""
    if callback.from_user.id not in SUPPORT_IDS + SUPER_ADMIN_IDS:
        await callback.answer("❌ У вас нет прав для этого действия.")
        return

    complaint_id = int(callback.data.split(":")[1])

    db = SessionLocal()
    try:
        complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
        if not complaint:
            await callback.answer("❌ Жалоба не найдена.")
            return

        complaint.status = "resolved"
        complaint.is_resolved = True
        complaint.reviewed_by = callback.from_user.id
        complaint.reviewed_at = datetime.utcnow()

        db.commit()

        await callback.answer("✅ Жалоба разрешена!")
        await callback.message.edit_text(
            callback.message.text + "\n\n✅ <b>Жалоба разрешена</b>", parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Ошибка при разрешении жалобы: {e}")
        await callback.answer("❌ Ошибка при разрешении жалобы.")
    finally:
        db.close()


@router.callback_query(F.data.startswith("strike_user:"))
async def strike_user(callback: CallbackQuery):
    """Выдает страйк пользователю"""
    if callback.from_user.id not in SUPPORT_IDS + SUPER_ADMIN_IDS:
        await callback.answer("❌ У вас нет прав для этого действия.")
        return

    user_id = int(callback.data.split(":")[1])

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            await callback.answer("❌ Пользователь не найден.")
            return

        user.strikes += 1

        if user.strikes >= 3:
            user.is_banned = True
            status_text = "❌ Пользователь заблокирован (3 страйка)"
        else:
            status_text = f"⚠️ Пользователю выдан страйк ({user.strikes}/3)"

        db.commit()

        await callback.answer(status_text)
        await callback.message.edit_text(
            callback.message.text + f"\n\n{status_text}", parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Ошибка при выдаче страйка: {e}")
        await callback.answer("❌ Ошибка при выдаче страйка.")
    finally:
        db.close()
