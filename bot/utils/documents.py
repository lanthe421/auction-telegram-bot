import json
import os
from datetime import datetime
from pathlib import Path

from database.db import SessionLocal
from database.models import Document, DocumentType, Lot, User

# Путь к шаблонам
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def load_template(template_name: str) -> str:
    """Загружает шаблон документа"""
    template_path = TEMPLATES_DIR / template_name
    if template_path.exists():
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    else:
        raise FileNotFoundError(f"Шаблон {template_name} не найден")


def generate_document_number() -> str:
    """Генерирует уникальный номер документа"""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"DOC-{timestamp}"


def format_document(lot: Lot, buyer: User, template_content: str) -> str:
    """Форматирует документ с данными лота и покупателя"""
    db = SessionLocal()
    try:
        seller = db.query(User).filter(User.id == lot.seller_id).first()

        # Базовые данные
        data = {
            "date": datetime.now().strftime("%d.%m.%Y"),
            "document_number": generate_document_number(),
            "lot_title": lot.title,
            "lot_description": lot.description,
            "starting_price": f"{lot.starting_price:,.2f}",
            "final_price": f"{lot.current_price:,.2f}",
            "seller_name": f"{seller.first_name} {seller.last_name or ''}".strip(),
            "seller_username": seller.username or "N/A",
            "seller_id": seller.telegram_id,
            "buyer_name": f"{buyer.first_name} {buyer.last_name or ''}".strip(),
            "buyer_username": buyer.username or "N/A",
            "buyer_id": buyer.telegram_id,
            "commission_percent": 5.0,
            "commission_amount": f"{lot.current_price * 0.05:,.2f}",
            "total_amount": f"{lot.current_price * 1.05:,.2f}",
        }

        # Дополнительные данные в зависимости от типа документа
        if lot.document_type == DocumentType.JEWELRY:
            data.update(
                {
                    "material": "Золото 585 пробы",
                    "assay": "585",
                    "weight": "3.5",
                    "size": "18",
                    "condition": "Отличное",
                }
            )
        elif lot.document_type == DocumentType.HISTORICAL:
            data.update(
                {
                    "period": "XIX век",
                    "material": "Бронза",
                    "technique": "Литье",
                    "dimensions": "15x10x5 см",
                    "condition": "Хорошее",
                    "expert_opinion": "Подлинный предмет",
                    "authenticity_certificate": "Сертификат №12345",
                    "expert_report": "Экспертное заключение №67890",
                    "origin_certificate": "Сертификат происхождения №11111",
                    "expert_name": "Иванов И.И.",
                }
            )
        else:  # STANDARD
            data.update(
                {
                    "category": "Электроника",
                    "brand": "Apple",
                    "model": "iPhone 15 Pro",
                    "condition": "Новый",
                    "equipment": "Полная комплектация",
                }
            )

        # Заменяем плейсхолдеры в шаблоне
        formatted_doc = template_content
        for key, value in data.items():
            placeholder = f"{{{{{key}}}}}"
            formatted_doc = formatted_doc.replace(placeholder, str(value))

        return formatted_doc

    finally:
        db.close()


def create_document(lot: Lot, buyer: User) -> Document:
    """Создает документ подтверждения передачи прав"""
    db = SessionLocal()
    try:
        # Определяем шаблон по типу документа
        template_map = {
            DocumentType.JEWELRY: "jewelry.md",
            DocumentType.HISTORICAL: "historical.md",
            DocumentType.STANDARD: "standard.md",
        }

        template_name = template_map.get(lot.document_type, "standard.md")
        template_content = load_template(template_name)

        # Генерируем документ
        document_content = format_document(lot, buyer, template_content)

        # Сохраняем в базу данных
        document = Document(
            lot_id=lot.id, document_type=lot.document_type, content=document_content
        )

        db.add(document)
        db.commit()
        db.refresh(document)

        return document

    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_document_by_lot(lot_id: int) -> Document:
    """Получает документ по ID лота"""
    db = SessionLocal()
    try:
        return db.query(Document).filter(Document.lot_id == lot_id).first()
    finally:
        db.close()


def save_document_to_file(document: Document, file_path: str) -> bool:
    """Сохраняет документ в файл"""
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(document.content)
        return True
    except Exception as e:
        print(f"Ошибка сохранения документа: {e}")
        return False
