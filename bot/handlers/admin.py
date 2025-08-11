import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func

from bot.utils.keyboards import get_admin_keyboard, get_main_keyboard
from config.settings import ADMIN_IDS, SUPER_ADMIN_IDS
from database.db import SessionLocal
from database.models import Bid, Lot, LotStatus, Payment, User, UserRole

router = Router()
logger = logging.getLogger(__name__)


def _get_user_role_by_telegram_id(user_id: int) -> UserRole | None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        return user.role if user else None
    except Exception:
        return None
    finally:
        db.close()


def is_super_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь супер-администратором"""
    if user_id in SUPER_ADMIN_IDS:
        return True
    return _get_user_role_by_telegram_id(user_id) == UserRole.SUPER_ADMIN


def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором"""
    if user_id in ADMIN_IDS or user_id in SUPER_ADMIN_IDS:
        return True
    # Считаем админами тех, у кого роль SUPER_ADMIN в БД
    return _get_user_role_by_telegram_id(user_id) in {UserRole.SUPER_ADMIN}


# Команда /admin удалена по требованию. Доступ к админ-функциям оставлен через роль и кнопки.


@router.message(F.text == "📊 Статистика")
async def show_statistics(message: Message):
    """Показать статистику"""
    if not is_admin(message.from_user.id):
        return

    db = SessionLocal()
    try:
        # Подсчитываем статистику
        total_users = db.query(User).count()
        total_lots = db.query(Lot).count()
        active_lots = db.query(Lot).filter(Lot.status == LotStatus.ACTIVE).count()
        total_bids = db.query(Bid).count()
        total_payments = db.query(Payment).count()

        # Финансовая статистика
        total_revenue = (
            db.query(Payment)
            .filter(Payment.status == "completed")
            .with_entities(func.sum(Payment.amount))
            .scalar()
            or 0
        )

        text = f"""
📊 **Статистика платформы**

👥 **Пользователи:**
• Всего пользователей: {total_users}
• Модераторов: {db.query(User).filter(User.role == UserRole.MODERATOR).count()}
• Поддержка: {db.query(User).filter(User.role == UserRole.SUPPORT).count()}

💰 **Финансы:**
• Всего ставок: {total_bids}
• Всего платежей: {total_payments}
• Общая выручка: {total_revenue:,.2f} ₽

📈 **Активность:**
• Сегодня: {datetime.now().strftime('%d.%m.%Y')}
• Время: {datetime.now().strftime('%H:%M')}
        """

        await message.answer(text)

    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        await message.answer("❌ Ошибка при получении статистики")
    finally:
        db.close()


@router.message(F.text == "👥 Управление пользователями")
async def show_users(message: Message):
    """Показать пользователей"""
    if not is_admin(message.from_user.id):
        return

    db = SessionLocal()
    try:
        # Получаем последних 10 пользователей
        recent_users = db.query(User).order_by(User.created_at.desc()).limit(10).all()

        text = "👥 **Последние пользователи:**\n\n"
        for user in recent_users:
            role_emoji = {
                UserRole.SELLER: "👤",
                UserRole.MODERATOR: "⚙️",
                UserRole.SUPPORT: "🔧",
                UserRole.SUPER_ADMIN: "👑",
            }
            emoji = role_emoji.get(user.role, "❓")

            text += f"{emoji} **{user.first_name}**\n"
            text += f"🔗 @{user.username or 'N/A'}\n"
            text += f"📅 Регистрация: {user.created_at.strftime('%d.%m.%Y')}\n"
            text += f"⚠️ Страйков: {user.strikes}/3\n\n"

        await message.answer(text)

    except Exception as e:
        logger.error(f"Ошибка при получении пользователей: {e}")
        await message.answer("❌ Ошибка при получении данных")
    finally:
        db.close()


@router.message(F.text == "🔧 Управление аукционами")
async def manage_auctions(message: Message):
    """Управление аукционами"""
    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "🔧 **Управление аукционами**\n\n"
        "Лоты создаются и управляются через PyQt5 приложение.\n"
        "Используйте панель продавца для создания лотов.\n"
        "Используйте панель модерации для одобрения лотов.\n\n"
        "💡 Все аукционы управляются через графический интерфейс."
    )


@router.message(F.text == "💰 Финансы")
async def show_finances(message: Message):
    """Показать финансовую статистику"""
    if not is_admin(message.from_user.id):
        return

    db = SessionLocal()
    try:
        # Финансовая статистика
        total_payments = db.query(Payment).count()
        completed_payments = (
            db.query(Payment).filter(Payment.status == "completed").count()
        )
        pending_payments = db.query(Payment).filter(Payment.status == "pending").count()

        total_revenue = (
            db.query(Payment)
            .filter(Payment.status == "completed")
            .with_entities(func.sum(Payment.amount))
            .scalar()
            or 0
        )

        commission_revenue = (
            db.query(Payment)
            .filter(Payment.status == "completed", Payment.payment_type == "commission")
            .with_entities(func.sum(Payment.amount))
            .scalar()
            or 0
        )

        avg_payment = (
            f"• Средний платеж: {total_revenue/completed_payments:,.2f} ₽"
            if completed_payments > 0
            else "• Средний платеж: 0 ₽"
        )

        text = "\n".join(
            [
                "💰 **Финансовая статистика**",
                "",
                "💳 **Платежи:**",
                f"• Всего платежей: {total_payments}",
                f"• Завершенных: {completed_payments}",
                f"• В обработке: {pending_payments}",
                "",
                "💰 **Выручка:**",
                f"• Общая выручка: {total_revenue:,.2f} ₽",
                f"• Комиссии: {commission_revenue:,.2f} ₽",
                f"• Чистая прибыль: {commission_revenue:,.2f} ₽",
                "",
                "📊 **Статистика:**",
                avg_payment,
            ]
        )

        await message.answer(text)

    except Exception as e:
        logger.error(f"Ошибка при получении финансов: {e}")
        await message.answer("❌ Ошибка при получении данных")
    finally:
        db.close()


@router.message(F.text == "⚙️ Настройки")
async def show_admin_settings(message: Message):
    """Показать настройки администратора"""
    if not is_admin(message.from_user.id):
        # Если пользователь не админ, не обрабатываем эту кнопку
        # Пусть её обработает обработчик в users.py
        return

    role_text = (
        "👑 Супер администратор"
        if is_super_admin(message.from_user.id)
        else "⚙️ Администратор"
    )

    text = f"""
⚙️ **Настройки администратора**

👤 **Роль:** {role_text}
🕐 **Время сервера:** {datetime.now().strftime('%d.%m.%Y %H:%M')}

🔧 **Доступные функции:**
• Управление пользователями
• Модерация лотов
• Финансовая статистика
• Система поддержки

💡 **Для изменения настроек используйте PyQt5 приложение.**
    """

    await message.answer(text)


@router.message(F.text == "🔙 Главное меню")
async def back_to_main_menu(message: Message):
    """Возврат в главное меню"""
    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "🎉 Добро пожаловать в аукционный бот!\n\n"
        "Здесь вы можете:\n"
        "• Участвовать в аукционах\n"
        "• Создавать свои лоты\n"
        "• Делать ставки\n"
        "• Отслеживать активные торги\n\n"
        "Используйте кнопки ниже для навигации:",
        reply_markup=get_main_keyboard(),
    )
