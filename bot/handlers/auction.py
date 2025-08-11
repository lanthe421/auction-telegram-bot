import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)
from sqlalchemy.orm import Session

from bot.utils.bid_calculator import calculate_min_bid, format_bid_info, validate_bid
from bot.utils.keyboards import (
    get_auction_keyboard,
    get_bid_keyboard,
    get_main_keyboard,
)
from bot.utils.lot_helpers import get_current_leader
from bot.utils.time_utils import get_moscow_time
from config.settings import TELEGRAM_CHANNEL_USERNAME
from database.db import SessionLocal, get_db
from database.models import Bid, Document, DocumentType, Lot, LotStatus, User, UserRole

router = Router()
logger = logging.getLogger(__name__)

from typing import Dict, Set, Tuple

# Кэш отправленных альбомов в чате: предотвращает повторные отправки при навигации
_sent_albums: Set[Tuple[int, int]] = set()

# Live-обновления убраны для улучшения производительности


# Функция удалена - live-обновления больше не используются


async def safe_edit_message(
    callback: CallbackQuery, text: str, reply_markup=None, parse_mode="HTML"
):
    """Безопасно редактирует сообщение с обработкой ошибок"""
    try:
        # Защита от пустого текста
        if not text or not str(text).strip():
            raise ValueError("empty_text_for_edit")
        await callback.message.edit_text(
            text, reply_markup=reply_markup, parse_mode=parse_mode
        )
    except Exception as e:
        err = str(e).lower()
        if "message is not modified" in err:
            return
        # Если сообщение без текста (например, фото с подписью) — пробуем отредактировать подпись
        if (
            "there is no text in the message to edit" in err
            or "message to edit has no text" in err
        ):
            try:
                await callback.message.edit_caption(
                    caption=text, reply_markup=reply_markup, parse_mode=parse_mode
                )
                return
            except Exception as cap_err:
                if "message is not modified" in str(cap_err).lower():
                    return
        logger.error("Ошибка при редактировании сообщения: %s", e)
        # Если не удалось отредактировать, отправляем новое сообщение
        safe_text = text if text and str(text).strip() else "Сообщение обновлено"
        await callback.message.answer(
            safe_text, reply_markup=reply_markup, parse_mode=parse_mode
        )


async def check_user_banned(user_id: int, message_or_callback) -> bool:
    """Проверяет, заблокирован ли пользователь"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if user and user.is_banned:
            ban_message = (
                "❌ **Доступ запрещен!**\n\n"
                "Ваш аккаунт заблокирован администратором.\n"
                "Обратитесь к администратору для разблокировки."
            )

            if hasattr(message_or_callback, "message"):
                # Это callback query
                await message_or_callback.answer(ban_message, parse_mode="Markdown")
            else:
                # Это message
                await message_or_callback.answer(ban_message, parse_mode="Markdown")

            return True
        return False
    except Exception as e:
        logger.error("Ошибка при проверке блокировки пользователя: %s", e)
        return False
    finally:
        db.close()


class AuctionStates(StatesGroup):
    """Состояния для создания аукциона"""

    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_price = State()
    waiting_for_duration = State()
    waiting_for_image = State()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    # Очищаем состояние FSM, если пользователь был в процессе ввода ставки
    from bot.utils.fsm_utils import clear_bid_state_if_needed

    if await clear_bid_state_if_needed(state):
        logger.info(
            f"Очищено состояние FSM для пользователя {message.from_user.id} при команде /start"
        )

    # Проверяем блокировку
    if await check_user_banned(message.from_user.id, message):
        return

    # Регистрируем пользователя
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
            return

        # Проверяем, есть ли параметр lot_id в команде
        args = message.text.split()
        if len(args) > 1:
            try:
                # Обрабатываем формат "lot_44" из ссылки
                param = args[1]
                if param.startswith("lot_"):
                    lot_id = int(param.split("_")[1])
                    await show_lot_from_start(message, lot_id)
                    return
                else:
                    # Пробуем старый формат (просто число)
                    lot_id = int(param)
                    await show_lot_from_start(message, lot_id)
                    return
            except (ValueError, IndexError):
                pass  # Если не удалось распарсить lot_id, показываем главное меню

        # Показываем главное меню
        welcome_text = (
            f"👋 Привет, {user.first_name}!\n\n"
            f"🏛️ Добро пожаловать в аукционный бот!\n\n"
            f"🎯 Здесь вы можете:\n"
            f"• Участвовать в аукционах\n"
            f"• Создавать свои лоты\n"
            f"• Отслеживать ставки\n"
            f"• Получать уведомления\n\n"
            f"Выберите действие:"
        )

        await message.answer(
            welcome_text,
            reply_markup=get_main_keyboard(),
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error("Ошибка при обработке команды start: %s", e)
        await message.answer("❌ Произошла ошибка при запуске бота")
    finally:
        db.close()


async def show_lot_from_start(message: Message, lot_id: int):
    """Показать лот при переходе по ссылке из канала"""
    db = next(get_db())

    try:
        lot = db.query(Lot).filter(Lot.id == lot_id).first()
        if not lot:
            await message.answer("❌ Лот не найден")
            return

        seller = db.query(User).filter(User.id == lot.seller_id).first()
        seller_name = seller.first_name or seller.username or "Неизвестно"

        # Получаем количество ставок
        bids_count = len(lot.bids)

        # Проверяем, активен ли лот (сравниваем в UTC) с нормализацией tz
        now_utc = datetime.now(timezone.utc)
        lot_end_utc = lot.end_time
        if lot_end_utc is not None and lot_end_utc.tzinfo is None:
            lot_end_utc = lot_end_utc.replace(tzinfo=timezone.utc)
        is_active = lot.status == LotStatus.ACTIVE and (
            lot_end_utc is None or lot_end_utc > now_utc
        )
        status = "🟢 Активен" if is_active else "🔴 Завершен"

        # Рассчитываем минимальную ставку по прогрессивной системе
        min_bid_amount = calculate_min_bid(lot.current_price)
        min_increment = min_bid_amount - lot.current_price

        # Лидер
        leader_name, leader_amount = get_current_leader(db, lot.id)

        # Форматируем время окончания по МСК для отображения
        from bot.utils.time_utils import utc_to_moscow

        end_time_text = (
            utc_to_moscow(lot.end_time).strftime("%d.%m.%Y %H:%M")
            if lot.end_time
            else "Не указано"
        )

        text = (
            f"🏷️ <b>{lot.title}</b>\n\n"
            f"📝 {lot.description or 'Описание отсутствует'}\n\n"
            f"💰 Текущая цена: <b>{lot.current_price}₽</b>\n"
            f"📈 Минимальная ставка: <b>{min_bid_amount:,.2f}₽</b> (шаг: {min_increment:,.2f}₽)\n"
            f"🥇 Лидер: {leader_name}{f' ({leader_amount:,.2f}₽)' if leader_amount is not None and leader_name != '—' else ''}\n"
            f"👤 Продавец: {seller_name}\n"
            f"📊 Ставок: {bids_count}\n"
            f"⏰ Завершение: {end_time_text}\n"
            f"📊 Статус: {status}"
        )

        if lot.images:
            # Если есть изображения — отправляем альбом или одно фото
            import json

            try:
                images = json.loads(lot.images)
                images = [img for img in images if img]
                if images and len(images) > 1:
                    cache_key = (message.chat.id, lot.id)
                    if cache_key not in _sent_albums:
                        media = []
                        for img_path in images:
                            try:
                                media.append(
                                    InputMediaPhoto(media=FSInputFile(img_path))
                                )
                            except Exception as e:
                                logger.warning(
                                    f"Ошибка подготовки изображения {img_path}: {e}"
                                )
                        if media:
                            try:
                                await message.bot.send_media_group(
                                    chat_id=message.chat.id, media=media
                                )
                                _sent_albums.add(cache_key)
                            except Exception as e:
                                logger.error(f"Ошибка отправки альбома в боте: {e}")
                    await message.answer(
                        text,
                        reply_markup=get_auction_keyboard(lot.id),
                        parse_mode="HTML",
                    )
                    return
                elif images:
                    await message.answer_photo(
                        photo=FSInputFile(images[0]),
                        caption=text,
                        reply_markup=get_auction_keyboard(lot.id),
                        parse_mode="HTML",
                    )
                    return
            except Exception as e:
                logger.error("Ошибка при обработке изображений: %s", e)

        await message.answer(
            text, reply_markup=get_auction_keyboard(lot.id), parse_mode="HTML"
        )

    except Exception as e:
        logger.error("Ошибка при получении деталей лота: %s", e)
        await message.answer("❌ Произошла ошибка")
    finally:
        db.close()


# Обработчик перенесен в users.py чтобы избежать дублирования


# Обработчик перенесен в users.py чтобы избежать дублирования


async def _render_lot_details(callback: CallbackQuery, lot_id: int) -> None:
    """Отрисовывает детали лота по его id (используется разными обработчиками)."""
    db = next(get_db())
    try:
        lot = db.query(Lot).filter(Lot.id == lot_id).first()
        if not lot:
            await callback.answer("❌ Лот не найден")
            return

        seller = db.query(User).filter(User.id == lot.seller_id).first()
        seller_name = seller.first_name or seller.username or "Неизвестно"

        bids_count = len(lot.bids)
        now_utc = datetime.now(timezone.utc)
        lot_end_utc = lot.end_time
        if lot_end_utc is not None and lot_end_utc.tzinfo is None:
            lot_end_utc = lot_end_utc.replace(tzinfo=timezone.utc)
        is_active = lot.status == LotStatus.ACTIVE and (
            lot_end_utc is None or lot_end_utc > now_utc
        )
        status = "🟢 Активен" if is_active else "🔴 Завершен"

        min_bid_amount = calculate_min_bid(lot.current_price)
        min_increment = min_bid_amount - lot.current_price
        leader_name, leader_amount = get_current_leader(db, lot.id)

        from bot.utils.time_utils import utc_to_moscow

        end_time_text = (
            utc_to_moscow(lot.end_time).strftime("%d.%m.%Y %H:%M")
            if lot.end_time
            else "Не указано"
        )

        text = (
            f"🏷️ <b>{lot.title}</b>\n\n"
            f"📝 {lot.description or 'Описание отсутствует'}\n\n"
            f"💰 Текущая цена: <b>{lot.current_price}₽</b>\n"
            f"📈 Минимальная ставка: <b>{min_bid_amount:,.2f}₽</b> (шаг: {min_increment:,.2f}₽)\n"
            f"🥇 Лидер: {leader_name}{f' ({leader_amount:,.2f}₽)' if leader_amount is not None and leader_name != '—' else ''}\n"
            f"👤 Продавец: {seller_name}\n"
            f"📊 Ставок: {bids_count}\n"
            f"⏰ Завершение: {end_time_text}\n"
            f"📊 Статус: {status}"
        )

        if lot.images:
            import json

            try:
                images = json.loads(lot.images)
                images = [img for img in images if img]
                if images and len(images) > 1:
                    cache_key = (callback.message.chat.id, lot.id)
                    if cache_key not in _sent_albums:
                        media = []
                        for img_path in images:
                            try:
                                media.append(
                                    InputMediaPhoto(media=FSInputFile(img_path))
                                )
                            except Exception as e:
                                logger.warning(
                                    f"Ошибка подготовки изображения {img_path}: {e}"
                                )
                        if media:
                            try:
                                await callback.message.bot.send_media_group(
                                    chat_id=callback.message.chat.id, media=media
                                )
                                _sent_albums.add(cache_key)
                            except Exception as e:
                                logger.error("Ошибка отправки альбома в боте: %s", e)
                    await safe_edit_message(
                        callback, text, reply_markup=get_auction_keyboard(lot.id)
                    )
                    await callback.answer()
                    return
                elif images:
                    await callback.message.edit_media(
                        media=InputMediaPhoto(
                            media=FSInputFile(images[0]),
                            caption=text,
                            parse_mode="HTML",
                        ),
                        reply_markup=get_auction_keyboard(lot.id),
                    )
                    await callback.answer()
                    return
            except Exception as e:
                logger.error("Ошибка при обработке изображений: %s", e)

        await safe_edit_message(
            callback, text, reply_markup=get_auction_keyboard(lot.id)
        )
        await callback.answer()
    except Exception as e:
        logger.error("Ошибка при получении деталей лота: %s", e)
        await callback.answer("❌ Произошла ошибка")
    finally:
        db.close()


@router.callback_query(F.data.startswith("lot:"))
async def show_lot_details(callback: CallbackQuery, state: FSMContext):
    """Показать детали лота"""
    # Очищаем состояние FSM, если пользователь был в процессе ввода ставки
    from bot.utils.fsm_utils import clear_bid_state_if_needed
    from bot.utils.safe_parsers import safe_extract_lot_id

    if await clear_bid_state_if_needed(state):
        logger.info(
            f"Очищено состояние FSM для пользователя {callback.from_user.id} при открытии лота"
        )

    lot_id = safe_extract_lot_id(callback.data)
    if lot_id is None:
        await callback.answer("❌ Некорректный идентификатор лота", show_alert=True)
        return

    await _render_lot_details(callback, lot_id)


@router.callback_query(F.data.startswith("lot_details:"))
async def show_lot_details_from_back_button(callback: CallbackQuery, state: FSMContext):
    """Показать детали лота при нажатии кнопки 'Назад к лоту'"""
    # Очищаем состояние FSM, если пользователь был в процессе ввода ставки
    from bot.utils.fsm_utils import clear_bid_state_if_needed
    from bot.utils.safe_parsers import safe_extract_lot_id

    if await clear_bid_state_if_needed(state):
        logger.info(
            f"Очищено состояние FSM для пользователя {callback.from_user.id} при нажатии 'Назад к лоту'"
        )

    lot_id = safe_extract_lot_id(callback.data)
    if lot_id is None:
        await callback.answer("❌ Некорректный идентификатор лота", show_alert=True)
        return

    await _render_lot_details(callback, lot_id)


@router.callback_query(F.data.startswith("download_files:"))
async def download_lot_files(callback: CallbackQuery):
    """Скачать файлы лота (если прикреплены в панели продавца)"""
    from bot.utils.safe_parsers import safe_extract_lot_id

    lot_id = safe_extract_lot_id(callback.data)
    if lot_id is None:
        await callback.answer("❌ Некорректный идентификатор лота", show_alert=True)
        return
    db = next(get_db())

    try:
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not user:
            await callback.answer("❌ Пользователь не найден")
            return

        lot = db.query(Lot).filter(Lot.id == lot_id).first()
        if not lot:
            await callback.answer("❌ Лот не найден")
            return

        # Получаем прикрепленные файлы лота
        from management.utils.document_utils import ImageManager

        files = ImageManager.get_lot_files(lot)

        if not files:
            await callback.answer(
                "📁 Файлы для этого лота отсутствуют", show_alert=True
            )
            return

        # Отправляем каждый файл пользователю
        sent_any = False
        for file_path in files:
            try:
                await callback.message.answer_document(document=FSInputFile(file_path))
                sent_any = True
            except Exception as e:
                logger.error("Ошибка отправки файла %s: %s", file_path, e)

        if sent_any:
            await callback.answer("📁 Файлы отправлены")
        else:
            await callback.answer("❌ Не удалось отправить файлы", show_alert=True)

    except Exception as e:
        logger.error("Ошибка при скачивании файлов лота: %s", e)
        await callback.answer("❌ Произошла ошибка")
    finally:
        db.close()


@router.callback_query(F.data.startswith("download_transfer_doc:"))
async def download_transfer_document(callback: CallbackQuery):
    """Генерирует и отправляет документ передачи прав победителю"""
    from bot.utils.safe_parsers import safe_extract_lot_id

    lot_id = safe_extract_lot_id(callback.data)
    if lot_id is None:
        await callback.answer("❌ Некорректный идентификатор лота", show_alert=True)
        return
    db = next(get_db())
    try:
        # Находим лот и проверяем победителя
        lot = db.query(Lot).filter(Lot.id == lot_id).first()
        if not lot:
            await callback.answer("❌ Лот не найден", show_alert=True)
            return

        # Выигравшая ставка
        winning_bid = (
            db.query(Bid)
            .filter(Bid.lot_id == lot_id)
            .order_by(Bid.amount.desc())
            .first()
        )
        if not winning_bid:
            await callback.answer("❌ Победитель не найден", show_alert=True)
            return

        buyer = db.query(User).filter(User.id == winning_bid.bidder_id).first()
        seller = db.query(User).filter(User.id == lot.seller_id).first()

        if not buyer or not seller:
            await callback.answer(
                "❌ Данные продавца/покупателя не найдены", show_alert=True
            )
            return

        # Разрешаем скачивание только победителю
        if buyer.telegram_id != callback.from_user.id:
            await callback.answer(
                "❌ Документ доступен только победителю аукциона", show_alert=True
            )
            return

        # Генерация документа
        import os
        from pathlib import Path

        from bot.utils.documents import create_document, save_document_to_file

        document = create_document(lot, buyer)

        # Сохраняем временно в файл
        tmp_dir = Path("tmp_docs")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        file_path = tmp_dir / f"transfer_lot_{lot.id}_buyer_{buyer.id}.txt"
        save_document_to_file(document, str(file_path))

        # Отправляем документ
        try:
            await callback.message.answer_document(
                document=FSInputFile(str(file_path)),
                caption=f"📄 Документ передачи прав по лоту #{lot.id}",
            )
            await callback.answer("📄 Документ отправлен")
        except Exception as e:
            logger.error("Ошибка при отправке документа: %s", e)
            await callback.answer("❌ Ошибка при отправке документа", show_alert=True)
        finally:
            # Удаляем временный файл
            try:
                os.remove(file_path)
            except Exception:
                pass
    except Exception as e:
        logger.error("Ошибка при генерации документа передачи прав: %s", e)
        await callback.answer("❌ Ошибка при генерации документа", show_alert=True)
    finally:
        db.close()


@router.callback_query(F.data.startswith("contact_seller:"))
async def contact_seller(callback: CallbackQuery):
    """Связаться с продавцом"""
    from bot.utils.safe_parsers import safe_extract_lot_id

    lot_id = safe_extract_lot_id(callback.data)
    if lot_id is None:
        await callback.answer("❌ Некорректный идентификатор лота", show_alert=True)
        return
    db = next(get_db())

    try:
        lot = db.query(Lot).filter(Lot.id == lot_id).first()
        if not lot:
            await callback.answer("❌ Лот не найден", show_alert=True)
            return

        seller = db.query(User).filter(User.id == lot.seller_id).first()
        if not seller:
            await callback.answer("❌ Продавец не найден", show_alert=True)
            return

            # Проверяем, вызван ли callback из канала или из бота
        if callback.message.chat.type in ["channel", "supergroup"]:
            # Если это канал, показываем всплывающее уведомление
            contact_info = f"""📞 КОНТАКТЫ ПРОДАВЦА

🏷️ Лот: {lot.title}
👤 Продавец: {seller.first_name}
🔗 @{seller.username or 'N/A'}
📱 ID: {seller.telegram_id}

{f'🔗 Ссылка: {lot.seller_link}' if lot.seller_link else ''}

💡 Для связи напишите продавцу в Telegram и укажите номер лота #{lot_id}"""

            await callback.answer(contact_info, show_alert=True)
        else:
            # Если это бот, показываем полную информацию с кнопкой "Назад"
            text = f"""
📞 <b>СВЯЗЬ С ПРОДАВЦОМ</b>

🏷️ <b>Лот:</b> {lot.title}

👤 <b>Продавец:</b> {seller.first_name}
🔗 <b>Username:</b> @{seller.username or 'N/A'}
📱 <b>Telegram ID:</b> {seller.telegram_id}

{f'🔗 <b>Ссылка на продавца:</b> {lot.seller_link}' if lot.seller_link else ''}

💡 <b>Для связи:</b>
• Напишите продавцу в Telegram
• Укажите номер лота #{lot_id}
• Обсудите условия передачи товара
            """.strip()

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

            # Редактируем сообщение с контактами продавца
            await safe_edit_message(callback, text, reply_markup=keyboard)
            await callback.answer()

    except Exception as e:
        logger.error("Ошибка при получении контактов продавца: %s", e)
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        db.close()


@router.callback_query(F.data.startswith("time_remaining:"))
async def time_remaining_colon(callback: CallbackQuery):
    """Показывает оставшееся время до окончания аукциона (всплывающее окно)."""
    from bot.utils.safe_parsers import safe_extract_lot_id

    lot_id = safe_extract_lot_id(callback.data)
    if lot_id is None:
        await callback.answer("❌ Некорректный идентификатор лота", show_alert=True)
        return

    db = next(get_db())
    try:
        lot = db.query(Lot).filter(Lot.id == lot_id).first()
        if not lot:
            await callback.answer("❌ Лот не найден", show_alert=True)
            return

        if not lot.end_time:
            await callback.answer("⏰ Время окончания не указано", show_alert=True)
            return

        # Считаем оставшееся время в МСК
        from bot.utils.time_utils import utc_to_moscow

        now = get_moscow_time()
        lot_end_msk = utc_to_moscow(lot.end_time)
        remaining = lot_end_msk - now
        total_seconds = int(remaining.total_seconds())
        if total_seconds <= 0:
            await callback.answer("⏰ Аукцион завершен", show_alert=True)
            return

        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        parts = []
        if days:
            parts.append(f"{days} д")
        parts.append(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        end_str = lot_end_msk.strftime("%d.%m.%Y %H:%M")
        text = f"⏰ До окончания: {' '.join(parts)}\n📅 Окончание: {end_str}"
        await callback.answer(text, show_alert=True)
    except Exception as e:
        logger.error("Ошибка при обработке time_remaining: %s", e)
        await callback.answer("❌ Ошибка", show_alert=True)
    finally:
        db.close()


@router.callback_query(F.data.startswith("time_remaining_"))
async def time_remaining_underscore(callback: CallbackQuery):
    """Совместимость с клавиатурами, где используется подчеркивание в callback_data."""
    from bot.utils.safe_parsers import safe_extract_id

    lot_id = safe_extract_id(callback.data, "_", 1)
    if lot_id is None:
        await callback.answer("❌ Некорректный идентификатор лота", show_alert=True)
        return

    # Делегируем в основной обработчик
    class Dummy:
        data = f"time_remaining:{lot_id}"

    await time_remaining_colon(
        CallbackQuery(model=callback.model_copy(update={"data": Dummy.data}))
    )


@router.callback_query(F.data.startswith("contact_seller_"))
async def contact_seller_underscore(callback: CallbackQuery):
    """Совместимость с клавиатурами с подчеркиванием в callback_data (contact_seller_)."""
    from bot.utils.safe_parsers import safe_extract_id

    lot_id = safe_extract_id(callback.data, "_", 1)
    if lot_id is None:
        await callback.answer("❌ Некорректный идентификатор лота", show_alert=True)
        return

    # Делегируем в основной обработчик
    class Dummy:
        data = f"contact_seller:{lot_id}"

    await contact_seller(
        CallbackQuery(model=callback.model_copy(update={"data": Dummy.data}))
    )


@router.callback_query(F.data.startswith("participate:"))
async def participate_in_auction(callback: CallbackQuery):
    """Обработчик кнопки 'Участвовать'"""
    # Проверяем блокировку пользователя
    if await check_user_banned(callback.from_user.id, callback):
        return

    from bot.utils.safe_parsers import safe_extract_lot_id

    lot_id = safe_extract_lot_id(callback.data)
    if lot_id is None:
        await callback.answer("❌ Некорректный идентификатор лота", show_alert=True)
        return
    db = next(get_db())

    try:
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not user:
            await callback.answer("❌ Пользователь не найден")
            return

        lot = db.query(Lot).filter(Lot.id == lot_id).first()
        if not lot:
            await callback.answer("❌ Лот не найден")
            return

        # Проверяем, активен ли лот
        now_utc = datetime.now(timezone.utc)
        lot_end_utc = lot.end_time
        if lot_end_utc is not None and lot_end_utc.tzinfo is None:
            lot_end_utc = lot_end_utc.replace(tzinfo=timezone.utc)
        if lot.status != LotStatus.ACTIVE or (
            lot_end_utc is not None and lot_end_utc <= now_utc
        ):
            await callback.answer("❌ Аукцион завершен")
            return

        # Проверяем, не является ли пользователь продавцом
        if user.id == lot.seller_id:
            await callback.answer("❌ Вы не можете участвовать в своем лоте")
            return

        # Показываем детали лота для участия
        seller = db.query(User).filter(User.id == lot.seller_id).first()
        seller_name = seller.first_name or seller.username or "Неизвестно"

        bids_count = len(lot.bids)

        # Рассчитываем минимальную ставку по прогрессивной системе
        min_bid_amount = calculate_min_bid(lot.current_price)
        min_increment = min_bid_amount - lot.current_price

        from bot.utils.time_utils import utc_to_moscow

        end_time_text = (
            utc_to_moscow(lot.end_time).strftime("%d.%m.%Y %H:%M")
            if lot.end_time
            else "Не указано"
        )

        text = f"""
🎯 <b>УЧАСТИЕ В АУКЦИОНЕ</b>

🏷️ <b>{lot.title}</b>

📝 <b>Описание:</b>
{lot.description}

💰 <b>Стартовая цена:</b> {lot.starting_price:,.2f} ₽
💰 <b>Текущая цена:</b> {lot.current_price:,.2f} ₽
📈 <b>Минимальная ставка:</b> {min_bid_amount:,.2f} ₽ (шаг: {min_increment:,.2f} ₽)

 🥇 <b>Лидер:</b> {get_current_leader(db, lot.id)[0]}{f" ({get_current_leader(db, lot.id)[1]:,.2f} ₽)" if get_current_leader(db, lot.id)[1] else ''}

👤 <b>Продавец:</b> {seller_name}
📊 <b>Ставок:</b> {bids_count}
⏰ <b>Окончание:</b> {end_time_text}

📍 <b>Геолокация:</b> {lot.location or 'Не указана'}
🔗 <b>Ссылка на продавца:</b> {lot.seller_link or 'Не указана'}
        """.strip()

        # Создаем клавиатуру для участия
        from bot.utils.keyboards import get_bid_keyboard

        keyboard = get_bid_keyboard(lot.id, lot.current_price)

        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()

    except Exception as e:
        logger.error("Ошибка при участии в аукционе: %s", e)
        await callback.answer("❌ Произошла ошибка")
    finally:
        db.close()


@router.callback_query(F.data.startswith("bid:"))
async def show_bid_options(callback: CallbackQuery):
    """Показать опции для ставки"""
    # Проверяем блокировку пользователя
    if await check_user_banned(callback.from_user.id, callback):
        return

    from bot.utils.safe_parsers import safe_extract_lot_id

    lot_id = safe_extract_lot_id(callback.data)
    if lot_id is None:
        await callback.answer("❌ Некорректный идентификатор лота", show_alert=True)
        return

    db = next(get_db())

    try:
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not user:
            await callback.answer("❌ Пользователь не найден")
            return

        lot = db.query(Lot).filter(Lot.id == lot_id).first()
        if not lot:
            await callback.answer("❌ Лот не найден")
            return

        # Проверяем, активен ли лот
        now_utc = datetime.now(timezone.utc)
        lot_end_utc = lot.end_time
        if lot_end_utc is not None and lot_end_utc.tzinfo is None:
            lot_end_utc = lot_end_utc.replace(tzinfo=timezone.utc)
        if lot.status != LotStatus.ACTIVE or (
            lot_end_utc is not None and lot_end_utc <= now_utc
        ):
            await callback.answer("❌ Аукцион завершен")
            return

        # Форматируем информацию о ставках
        bid_info = format_bid_info(lot.current_price)

        # Редактируем текущее сообщение с опциями ставок
        bid_text = (
            f"💰 <b>Сделать ставку</b>\n\n"
            f"🏷️ <b>Лот:</b> {lot.title}\n\n"
            f"{bid_info}\n\n"
            f"🥇 <b>Лидер:</b> {get_current_leader(db, lot.id)[0]}"
        )
        # Добавляем сумму лидера, если есть, безопасно, чтобы исключить None
        leader = get_current_leader(db, lot.id)
        if leader and leader[1] is not None:
            bid_text += f" ({leader[1]:,.2f} ₽)"
        bid_keyboard = get_bid_keyboard(
            lot.id, lot.current_price, user.id if user else None
        )

        # Перед сменой экрана останавливаем возможное предыдущее live-обновление этого сообщения
        # Live-обновления больше не используются

        await safe_edit_message(callback, bid_text, reply_markup=bid_keyboard)

        # Live-обновления убраны для улучшения производительности

    except Exception as e:
        logger.error("Ошибка при создании ставки: %s", e)
        await callback.answer("❌ Ошибка")
    finally:
        db.close()


@router.callback_query(F.data.startswith("seller_contact:"))
async def seller_contact_colon(callback: CallbackQuery):
    """Совместимость с уведомлениями, использующими seller_contact:"""
    from bot.utils.safe_parsers import safe_extract_lot_id

    lot_id = safe_extract_lot_id(callback.data)
    if lot_id is None:
        await callback.answer("❌ Некорректный идентификатор лота", show_alert=True)
        return

    # Делегируем в основной обработчик contact_seller
    class Dummy:
        data = f"contact_seller:{lot_id}"

    await contact_seller(
        CallbackQuery(model=callback.model_copy(update={"data": Dummy.data}))
    )
