import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from database.models import Document, DocumentType, Lot, User

logger = logging.getLogger(__name__)


class DocumentGenerator:
    """Генератор документов для подтверждения передачи прав на лот"""

    def __init__(self):
        self.templates_dir = Path("bot/templates/documents")
        self.templates_dir.mkdir(parents=True, exist_ok=True)

        # Шаблоны документов
        self.templates = {
            DocumentType.JEWELRY: self._get_jewelry_template(),
            DocumentType.HISTORICAL: self._get_historical_template(),
            DocumentType.STANDARD: self._get_standard_template(),
        }

    def generate_document(
        self,
        lot: Lot,
        seller: User,
        buyer: User,
        final_price: float,
        document_type: DocumentType,
    ) -> Document:
        """Генерирует документ подтверждения передачи прав"""

        # Получаем шаблон
        template = self.templates.get(
            document_type, self.templates[DocumentType.STANDARD]
        )

        # Заполняем шаблон данными
        content = self._fill_template(template, lot, seller, buyer, final_price)

        # Создаем документ в базе данных
        document = Document(
            lot_id=lot.id,
            document_type=document_type,
            content=content,
            file_path=None,  # Пока без файла
        )

        logger.info(f"Документ для лота {lot.id} создан (тип: {document_type.value})")
        return document

    def _fill_template(
        self, template: str, lot: Lot, seller: User, buyer: User, final_price: float
    ) -> str:
        """Заполняет шаблон данными"""

        # Форматируем дату
        current_date = datetime.now().strftime("%d.%m.%Y")
        current_time = datetime.now().strftime("%H:%M")

        # Форматируем цену
        price_formatted = f"{final_price:,.2f} ₽"

        # Заменяем плейсхолдеры
        content = template.replace("{current_date}", current_date)
        content = content.replace("{current_time}", current_time)
        content = content.replace("{lot_id}", str(lot.id))
        content = content.replace("{lot_title}", lot.title)
        content = content.replace("{lot_description}", lot.description)
        content = content.replace("{starting_price}", f"{lot.starting_price:,.2f} ₽")
        content = content.replace("{final_price}", price_formatted)
        content = content.replace(
            "{seller_name}", f"{seller.first_name} {seller.last_name or ''}"
        )
        content = content.replace("{seller_username}", seller.username or "N/A")
        content = content.replace("{seller_telegram_id}", str(seller.telegram_id))
        content = content.replace(
            "{buyer_name}", f"{buyer.first_name} {buyer.last_name or ''}"
        )
        content = content.replace("{buyer_username}", buyer.username or "N/A")
        content = content.replace("{buyer_telegram_id}", str(buyer.telegram_id))
        content = content.replace(
            "{start_time}", lot.start_time.strftime("%d.%m.%Y %H:%M") if lot.start_time else "Немедленно"
        )
        content = content.replace("{end_time}", lot.end_time.strftime("%d.%m.%Y %H:%M") if lot.end_time else "Не определено")

        # Добавляем геолокацию если есть
        if lot.location:
            content = content.replace("{location}", lot.location)
        else:
            content = content.replace("{location}", "Не указана")

        return content

    def _get_jewelry_template(self) -> str:
        """Шаблон для ювелирных изделий"""
        return """
# АКТ ПЕРЕДАЧИ ЮВЕЛИРНОГО ИЗДЕЛИЯ

**Дата и время составления:** {current_date} в {current_time}

## ИНФОРМАЦИЯ О ЛОТЕ
- **Номер лота:** #{lot_id}
- **Наименование:** {lot_title}
- **Описание:** {lot_description}
- **Стартовая цена:** {starting_price}
- **Финальная цена:** {final_price}
- **Геолокация:** {location}

## ВРЕМЯ ПРОВЕДЕНИЯ АУКЦИОНА
- **Начало:** {start_time}
- **Окончание:** {end_time}

## ИНФОРМАЦИЯ О ПРОДАВЦЕ
- **ФИО:** {seller_name}
- **Username:** @{seller_username}
- **Telegram ID:** {seller_telegram_id}

## ИНФОРМАЦИЯ О ПОКУПАТЕЛЕ
- **ФИО:** {buyer_name}
- **Username:** @{buyer_username}
- **Telegram ID:** {buyer_telegram_id}

## УСЛОВИЯ ПЕРЕДАЧИ
1. Продавец обязуется передать ювелирное изделие в состоянии, соответствующем описанию лота
2. Покупатель обязуется оплатить финальную стоимость лота
3. Передача изделия осуществляется по согласованию сторон
4. Все претензии по качеству изделия рассматриваются в течение 24 часов после передачи

## ПОДПИСИ СТОРОН
- **Продавец:** _________________ (подпись)
- **Покупатель:** _________________ (подпись)

---
*Документ сгенерирован автоматически системой аукциона*
        """.strip()

    def _get_historical_template(self) -> str:
        """Шаблон для исторических ценностей"""
        return """
# АКТ ПЕРЕДАЧИ ИСТОРИЧЕСКОЙ ЦЕННОСТИ

**Дата и время составления:** {current_date} в {current_time}

## ИНФОРМАЦИЯ О ЛОТЕ
- **Номер лота:** #{lot_id}
- **Наименование:** {lot_title}
- **Описание:** {lot_description}
- **Стартовая цена:** {starting_price}
- **Финальная цена:** {final_price}
- **Геолокация:** {location}

## ВРЕМЯ ПРОВЕДЕНИЯ АУКЦИОНА
- **Начало:** {start_time}
- **Окончание:** {end_time}

## ИНФОРМАЦИЯ О ПРОДАВЦЕ
- **ФИО:** {seller_name}
- **Username:** @{seller_username}
- **Telegram ID:** {seller_telegram_id}

## ИНФОРМАЦИЯ О ПОКУПАТЕЛЕ
- **ФИО:** {buyer_name}
- **Username:** @{buyer_username}
- **Telegram ID:** {buyer_telegram_id}

## ОСОБЫЕ УСЛОВИЯ ДЛЯ ИСТОРИЧЕСКИХ ЦЕННОСТЕЙ
1. Продавец подтверждает законность происхождения исторической ценности
2. Покупатель обязуется соблюдать требования по хранению и экспонированию
3. Передача осуществляется с соблюдением всех требований безопасности
4. Все сертификаты и документы передаются вместе с ценностью

## ПОДПИСИ СТОРОН
- **Продавец:** _________________ (подпись)
- **Покупатель:** _________________ (подпись)

---
*Документ сгенерирован автоматически системой аукциона*
        """.strip()

    def _get_standard_template(self) -> str:
        """Шаблон для стандартных лотов"""
        return """
# АКТ ПЕРЕДАЧИ ТОВАРА

**Дата и время составления:** {current_date} в {current_time}

## ИНФОРМАЦИЯ О ЛОТЕ
- **Номер лота:** #{lot_id}
- **Наименование:** {lot_title}
- **Описание:** {lot_description}
- **Стартовая цена:** {starting_price}
- **Финальная цена:** {final_price}
- **Геолокация:** {location}

## ВРЕМЯ ПРОВЕДЕНИЯ АУКЦИОНА
- **Начало:** {start_time}
- **Окончание:** {end_time}

## ИНФОРМАЦИЯ О ПРОДАВЦЕ
- **ФИО:** {seller_name}
- **Username:** @{seller_username}
- **Telegram ID:** {seller_telegram_id}

## ИНФОРМАЦИЯ О ПОКУПАТЕЛЕ
- **ФИО:** {buyer_name}
- **Username:** @{buyer_username}
- **Telegram ID:** {buyer_telegram_id}

## УСЛОВИЯ ПЕРЕДАЧИ
1. Продавец обязуется передать товар в состоянии, соответствующем описанию лота
2. Покупатель обязуется оплатить финальную стоимость лота
3. Передача товара осуществляется по согласованию сторон
4. Все претензии по качеству товара рассматриваются в течение 48 часов после передачи

## ПОДПИСИ СТОРОН
- **Продавец:** _________________ (подпись)
- **Покупатель:** _________________ (подпись)

---
*Документ сгенерирован автоматически системой аукциона*
        """.strip()

    def get_document_types_keyboard(self) -> Dict[str, str]:
        """Возвращает клавиатуру для выбора типа документа"""
        return {
            "jewelry": "💎 Ювелирные изделия",
            "historical": "🏛️ Исторические ценности",
            "standard": "📦 Стандартные лоты",
        }


# Создаем глобальный экземпляр
document_generator = DocumentGenerator()
