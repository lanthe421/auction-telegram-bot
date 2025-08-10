"""
Синхронная версия модуля для публикации лотов в Telegram группы
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

from bot.utils.lot_helpers import get_current_leader
from config.settings import (
    BOT_TOKEN,
    BOT_USERNAME,
    TELEGRAM_API_TIMEOUT,
    TELEGRAM_GROUP_ID,
    TELEGRAM_RETRY_DELAY,
)
from database.db import SessionLocal
from database.models import Bid, Lot, LotStatus, User

logger = logging.getLogger(__name__)


class TelegramPublisherSync:
    """Синхронный класс для публикации лотов в Telegram канал"""

    def __init__(self):
        self.group_id = TELEGRAM_GROUP_ID
        self._published_lots = set()
        # Антифлуд для синхронных запросов
        self.cooldown_until_ts: float = 0.0

    def _respect_cooldown(self):
        import time

        now = time.time()
        if self.cooldown_until_ts and now < self.cooldown_until_ts:
            time.sleep(max(self.cooldown_until_ts - now, 1))

    def _make_request(self, method: str, data: dict = None) -> dict:
        """Выполняет HTTP запрос к Telegram API"""
        try:
            self._respect_cooldown()
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
            response = requests.post(url, json=data, timeout=TELEGRAM_API_TIMEOUT)
            if response.status_code == 429:
                # Обрабатываем Too Many Requests
                try:
                    body = response.json()
                    retry_after = (
                        body.get("parameters", {}).get("retry_after")
                        or body.get("retry_after")
                        or 30
                    )
                except Exception:
                    retry_after = 30
                import time

                self.cooldown_until_ts = time.time() + float(retry_after)
                time.sleep(float(retry_after))
                # Одна повторная попытка после паузы
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
                response = requests.post(url, json=data, timeout=TELEGRAM_API_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            # Логируем детали ошибки для диагностики
            error_details = getattr(e, "response", None)
            if error_details and hasattr(error_details, "text"):
                logger.error(f"Ошибка HTTP запроса к Telegram API: {e}")
                logger.error(f"Детали ответа: {error_details.text}")
                # Пытаемся распарсить JSON ответ для более детальной информации
                try:
                    error_json = error_details.json()
                    logger.error(f"JSON ошибки: {error_json}")
                except:
                    pass
            else:
                logger.error(f"Ошибка HTTP запроса к Telegram API: {e}")
            raise e

    def _make_request_with_files(
        self, method: str, data: dict = None, files: dict = None
    ) -> dict:
        """Выполняет HTTP запрос к Telegram API с файлами"""
        try:
            self._respect_cooldown()
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
            response = requests.post(
                url, data=data, files=files, timeout=TELEGRAM_API_TIMEOUT
            )
            if response.status_code == 429:
                # Обрабатываем Too Many Requests
                try:
                    body = response.json()
                    retry_after = (
                        body.get("parameters", {}).get("retry_after")
                        or body.get("retry_after")
                        or 30
                    )
                except Exception:
                    retry_after = 30
                import time

                self.cooldown_until_ts = time.time() + float(retry_after)
                time.sleep(float(retry_after))
                # Одна повторная попытка после паузы
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
                response = requests.post(
                    url, data=data, files=files, timeout=TELEGRAM_API_TIMEOUT
                )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка HTTP запроса к Telegram API с файлами: {e}")
            raise e

    def publish_lot(self, lot_id: int, retry_count: int = 3) -> bool:
        """Публикует лот в Telegram канал с повторными попытками"""

        # Проверяем, не был ли лот уже опубликован
        if lot_id in self._published_lots:
            logger.info(f"Лот {lot_id} уже был опубликован")
            return True

        for attempt in range(retry_count):
            try:
                db = SessionLocal()
                lot = db.query(Lot).filter(Lot.id == lot_id).first()

                if not lot:
                    logger.error(f"Лот {lot_id} не найден")
                    return False

                if lot.status != LotStatus.ACTIVE:
                    logger.error(f"Лот {lot_id} не активен (статус: {lot.status})")
                    return False

                # Получаем информацию о продавце
                seller = db.query(User).filter(User.id == lot.seller_id).first()
                seller_name = seller.first_name if seller else "Неизвестно"

                # Создаем текст сообщения
                message_text = self.create_lot_message(lot, seller_name)

                # Создаем клавиатуру
                keyboard = self.create_lot_keyboard(lot.id)

                # Проверяем наличие изображений
                images = []
                if lot.images:
                    try:
                        images = json.loads(lot.images)
                        images = [img for img in images if os.path.exists(img)]
                    except:
                        logger.warning(
                            f"Ошибка при парсинге изображений для лота {lot_id}"
                        )

                # Публикуем в канал
                if images and len(images) > 1:
                    logger.info(
                        f"[SYNC] Публикация альбома: найдено {len(images)} файлов: {images}"
                    )
                    # Формируем media group и файлы для отправки через HTTP API
                    media_group: List[dict] = []
                    files_to_send: Dict[str, Any] = {}
                    open_file_handles: List[Any] = []
                    for i, image_path in enumerate(images):
                        if not os.path.exists(image_path):
                            logger.warning(f"[SYNC] Файл не найден: {image_path}")
                            continue
                        try:
                            media_group.append(
                                {"type": "photo", "media": f"attach://photo_{i}"}
                            )
                            fh = open(image_path, "rb")
                            open_file_handles.append(fh)
                            files_to_send[f"photo_{i}"] = fh
                        except Exception as e:
                            logger.warning(
                                f"[SYNC] Ошибка при подготовке изображения {image_path}: {e}"
                            )

                    logger.info(
                        f"[SYNC] Формируем альбом из {len(media_group)} файлов."
                    )
                    try:
                        media_response = self._make_request_with_files(
                            "sendMediaGroup",
                            {
                                "chat_id": self.group_id,
                                "media": json.dumps(media_group),
                            },
                            files_to_send,
                        )
                        if not media_response.get("ok"):
                            logger.error(
                                f"[SYNC] Ошибка при отправке медиа-группы: {media_response}"
                            )
                            return False
                        # Короткая сводка вместо полного JSON
                        result_items = media_response.get("result", []) or []
                        media_group_id = (
                            result_items[0].get("media_group_id")
                            if result_items
                            else None
                        )
                        logger.info(
                            f"[SYNC] Альбом отправлен: сообщений={len(result_items)}, media_group_id={media_group_id}"
                        )
                    finally:
                        # Гарантируем закрытие файловых дескрипторов
                        for fh in open_file_handles:
                            try:
                                fh.close()
                            except Exception:
                                pass

                    # После альбома отправляем описание и кнопки отдельным сообщением
                    try:
                        message_data = {
                            "chat_id": self.group_id,
                            "text": message_text,
                            "reply_markup": json.dumps(keyboard),
                            "parse_mode": "HTML",
                        }
                        response = self._make_request("sendMessage", message_data)
                        if response.get("ok"):
                            # Сохраняем message_id текстового сообщения, не альбома
                            lot.telegram_message_id = response["result"]["message_id"]
                            db.commit()
                            self._published_lots.add(lot_id)
                            logger.info(
                                f"Лот {lot_id} успешно опубликован в канал (попытка {attempt + 1}) - альбом + текст"
                            )
                            return True
                        else:
                            logger.error(
                                f"[SYNC] Ошибка при отправке описания: {response}"
                            )
                            return False
                    except Exception as e:
                        logger.error(f"[SYNC] Ошибка при отправке описания: {e}")
                        return False
                elif images:
                    try:
                        with open(images[0], "rb") as photo:
                            files = {"photo": photo}
                            data = {
                                "chat_id": self.group_id,
                                "caption": message_text,
                                "reply_markup": json.dumps(keyboard),
                                "parse_mode": "HTML",
                            }
                            response = self._make_request_with_files(
                                "sendPhoto", data, files
                            )
                            if response.get("ok"):
                                lot.telegram_message_id = response["result"][
                                    "message_id"
                                ]
                                db.commit()
                                self._published_lots.add(lot_id)
                                logger.info(
                                    f"Лот {lot_id} успешно опубликован в канал (попытка {attempt + 1})"
                                )
                                return True
                            else:
                                logger.error(f"Ошибка Telegram API: {response}")
                    except Exception as e:
                        logger.error(f"Ошибка при отправке фото: {e}")
                else:
                    # Если нет изображений, отправляем текстовое сообщение
                    data = {
                        "chat_id": self.group_id,
                        "text": message_text,
                        "reply_markup": json.dumps(keyboard),
                        "parse_mode": "HTML",
                    }
                    response = self._make_request("sendMessage", data)
                    if response.get("ok"):
                        lot.telegram_message_id = response["result"]["message_id"]
                        db.commit()
                        self._published_lots.add(lot_id)
                        logger.info(
                            f"Лот {lot_id} успешно опубликован в канал (попытка {attempt + 1})"
                        )
                        return True
                    else:
                        logger.error(f"Ошибка Telegram API: {response}")

            except Exception as e:
                logger.error(
                    f"Ошибка при публикации лота {lot_id} (попытка {attempt + 1}): {e}"
                )
                if attempt < retry_count - 1:
                    import time

                    time.sleep(TELEGRAM_RETRY_DELAY)
            finally:
                db.close()

        logger.error(
            f"Не удалось опубликовать лот {lot_id} после {retry_count} попыток"
        )
        return False

    def create_lot_message(self, lot: Lot, seller_name: str) -> str:
        """Создает текст сообщения для лота"""
        # Форматируем время
        start_time = (
            lot.start_time.strftime("%d.%m.%Y в %H:%M")
            if lot.start_time
            else "Немедленно"
        )
        end_time = (
            lot.end_time.strftime("%d.%m.%Y в %H:%M")
            if lot.end_time
            else "Не определено"
        )

        # Определяем тип документа
        doc_type_text = {
            "standard": "Стандартный лот",
            "jewelry": "Ювелирное изделие",
            "historical": "Историческая ценность",
        }.get(lot.document_type.value, "Стандартный лот")

        # Текущие ставки и лидер - используем функции из lot_helpers
        db = SessionLocal()
        try:
            from bot.utils.lot_helpers import (
                get_current_leader,
                get_fresh_bids_count,
                get_highest_fresh_bid_amount,
            )

            current_bids = get_fresh_bids_count(db, lot.id)
            highest_amount = get_highest_fresh_bid_amount(db, lot.id)

            # Если есть ставки, используем максимальную ставку, иначе стартовую цену
            if highest_amount is not None:
                current_price = highest_amount
            else:
                current_price = lot.starting_price

            leader_name, leader_amount = get_current_leader(db, lot.id)

        except Exception as e:
            logger.error(f"Ошибка при получении информации о ставках: {e}")
            current_bids = 0
            current_price = lot.current_price or lot.starting_price
            leader_name, leader_amount = "—", None
        finally:
            db.close()

        # Рассчитываем минимальную ставку по прогрессивной системе
        from bot.utils.bid_calculator import calculate_min_bid

        min_bid_amount = calculate_min_bid(current_price)
        min_increment = max(min_bid_amount - current_price, 0)

        message = f"""
🏛️ <b>НОВЫЙ ЛОТ #{lot.id}</b>

📦 <b>{lot.title}</b>

📝 <b>Описание:</b>
{lot.description}

💰 <b>Стартовая цена:</b> {lot.starting_price:,.2f} ₽
💎 <b>Текущая цена:</b> {current_price:,.2f} ₽
📊 <b>Количество ставок:</b> {current_bids}
🥇 <b>Лидер:</b> {leader_name}{f" ({leader_amount:,.2f} ₽)" if leader_amount is not None and leader_name != "—" else ''}

👤 <b>Продавец:</b> {seller_name}
📍 <b>Геолокация:</b> {lot.location or 'Не указана'}

📅 <b>Время старта:</b> {start_time}
⏰ <b>Время окончания:</b> {end_time}

📄 <b>Тип документа:</b> {doc_type_text}
🔗 <b>Ссылка на продавца:</b> {lot.seller_link or 'Не указана'}

💡 <b>Как участвовать:</b>
• Откройте лот в боте @{BOT_USERNAME} по кнопке ниже
• Минимальная ставка: {min_bid_amount:,.2f} ₽ (шаг: {min_increment:,.2f} ₽)
        """

        return message.strip()

    def create_lot_keyboard(self, lot_id: int) -> dict:
        """Клавиатура для канала: оставляем кнопки контакта/времени и deep-link."""
        return {
            "inline_keyboard": [
                [
                    {
                        "text": "📞 Связаться с продавцом",
                        "callback_data": f"contact_seller:{lot_id}",
                    },
                    {
                        "text": "⏰ Время окончания",
                        "callback_data": f"time_remaining:{lot_id}",
                    },
                ],
                [
                    {
                        "text": "🔗 Открыть лот",
                        "url": f"https://t.me/{BOT_USERNAME}?start=lot_{lot_id}",
                    }
                ],
            ]
        }

    def edit_lot_message(self, lot_id: int, message_id: int, new_text: str) -> bool:
        """Редактирует сообщение о лоте в канале"""
        if not new_text or not new_text.strip():
            logger.error(
                f"Попытка отредактировать сообщение на пустой текст для лота {lot_id}, message_id={message_id}"
            )
            return False
        try:
            data = {
                "chat_id": self.group_id,
                "message_id": message_id,
                "text": new_text,
                "parse_mode": "HTML",
            }
            response = self._make_request("editMessageText", data)
            if response.get("ok"):
                return True
            else:
                error_desc = response.get("description", "Неизвестная ошибка")
                if "message is not modified" in error_desc:
                    return True
                logger.error(
                    f"Ошибка при редактировании сообщения: {response}\nТекст: {new_text}\nmessage_id: {message_id}"
                )
                return False
        except Exception as e:
            error_str = str(e)
            if "message is not modified" in error_str:
                logger.info(
                    f"Сообщение о лоте {lot_id} не изменилось (контент идентичен)"
                )
                return True
            logger.error(
                f"Ошибка при редактировании сообщения о лоте {lot_id}: {e}\nТекст: {new_text}\nmessage_id: {message_id}"
            )
            return False

    def update_lot_message_with_bid(self, lot_id: int) -> bool:
        """Обновляет сообщение о лоте в канале при новой ставке"""
        try:
            db = SessionLocal()
            lot = db.query(Lot).filter(Lot.id == lot_id).first()

            if not lot or not lot.telegram_message_id:
                logger.error(f"Лот {lot_id} не найден или не имеет telegram_message_id")
                return False

            # Проверяем, есть ли у лота изображения (для определения типа публикации)
            images = []
            if lot.images:
                try:
                    images = json.loads(lot.images)
                    images = [img for img in images if os.path.exists(img)]
                except:
                    pass

            # Получаем информацию о продавце
            seller = db.query(User).filter(User.id == lot.seller_id).first()
            seller_name = seller.first_name if seller else "Неизвестно"

            # Создаем новый текст сообщения с обновленной ценой
            new_message_text = self.create_lot_message(lot, seller_name)

            # Создаем клавиатуру
            keyboard = self.create_lot_keyboard(lot.id)

            # Обновляем сообщение в канале
            # Пытаемся отредактировать текст; если было фото с подписью — редактируем подпись
            data = {
                "chat_id": self.group_id,
                "message_id": lot.telegram_message_id,
                "text": new_message_text,
                "reply_markup": json.dumps(keyboard),
                "parse_mode": "HTML",
            }
            response = None
            try:
                response = self._make_request("editMessageText", data)
            except requests.exceptions.RequestException as e:
                # Фолбэк на editMessageCaption для сообщений с фото
                err = str(e).lower()
                logger.warning(
                    f"Ошибка editMessageText для лота {lot_id}: {e}, пробуем editMessageCaption"
                )
                if (
                    "message is not modified" in err
                    or "message text was not modified" in err
                    or "bad request: message is not modified" in err
                ):
                    return True
                # Пробуем обновить подпись
                data_cap = {
                    "chat_id": self.group_id,
                    "message_id": lot.telegram_message_id,
                    "caption": new_message_text,
                    "reply_markup": json.dumps(keyboard),
                    "parse_mode": "HTML",
                }
                try:
                    response = self._make_request("editMessageCaption", data_cap)
                except Exception as cap_e:
                    logger.error(
                        f"Ошибка editMessageCaption для лота {lot_id}: {cap_e}"
                    )
                    response = None

            # Если обе попытки не дали ok, публикуем новое сообщение и обновляем message_id
            if not response or not response.get("ok"):
                logger.warning(
                    f"Не удалось отредактировать сообщение лота {lot_id}, отправляем новое"
                )
                try:
                    send_resp = self._make_request(
                        "sendMessage",
                        {
                            "chat_id": self.group_id,
                            "text": new_message_text,
                            "reply_markup": json.dumps(keyboard),
                            "parse_mode": "HTML",
                        },
                    )
                    if send_resp.get("ok"):
                        lot.telegram_message_id = send_resp["result"]["message_id"]
                        db.commit()
                        return True
                    else:
                        logger.error(
                            f"Не удалось отправить новое сообщение для лота {lot_id}: {send_resp}"
                        )
                        return False
                except Exception as send_e:
                    logger.error(
                        f"Ошибка при отправке нового сообщения для лота {lot_id}: {send_e}"
                    )
                    return False

            if response.get("ok"):
                return True
            else:
                error_desc = response.get("description", "Неизвестная ошибка")
                if "message is not modified" in error_desc:
                    return True
                logger.error(f"Ошибка при обновлении сообщения: {response}")
                return False

        except Exception as e:
            error_str = str(e)
            if "message is not modified" in error_str:
                return True
            logger.error(f"Ошибка при обновлении сообщения о лоте {lot_id}: {e}")
            return False
        finally:
            db.close()

    def send_lot_deleted_message(
        self, lot_id: int, lot_title: str, had_bids: bool
    ) -> bool:
        """Отправляет сообщение об удалении лота"""
        try:
            if had_bids:
                message_text = f"""
❌ <b>ЛОТ УДАЛЕН</b>

📦 <b>Лот #{lot_id}: {lot_title}</b>

⚠️ <b>Аукцион завершен досрочно</b>
📊 <b>Были сделаны ставки</b>

💡 <b>Причина:</b> Лот удален продавцом
                """
            else:
                message_text = f"""
❌ <b>ЛОТ УДАЛЕН</b>

📦 <b>Лот #{lot_id}: {lot_title}</b>

⚠️ <b>Аукцион завершен</b>
📊 <b>Победителей нет</b>

💡 <b>Причина:</b> Лот удален продавцом
                """

            data = {
                "chat_id": self.group_id,
                "text": message_text.strip(),
                "parse_mode": "HTML",
            }

            response = self._make_request("sendMessage", data)

            if response.get("ok"):
                logger.info(f"Сообщение об удалении лота {lot_id} отправлено")
                return True
            else:
                logger.error(f"Ошибка при отправке сообщения: {response}")
                return False

        except Exception as e:
            logger.error(
                f"Ошибка при отправке сообщения об удалении лота {lot_id}: {e}"
            )
            return False

    def clear_cache(self):
        """Очищает кэш опубликованных лотов"""
        self._published_lots.clear()
        logger.info("Кэш опубликованных лотов очищен")


# Глобальный экземпляр для использования в других модулях
telegram_publisher_sync = TelegramPublisherSync()
