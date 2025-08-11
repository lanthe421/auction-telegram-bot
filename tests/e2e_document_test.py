import os
import sys
from datetime import timedelta
from pathlib import Path

from bot.utils.documents import create_document, save_document_to_file
from bot.utils.time_utils import get_moscow_time
from database.db import SessionLocal
from database.models import Bid, DocumentType, Lot, LotStatus, User


def run():
    db = SessionLocal()
    seller = None
    buyer = None
    lot = None
    tmp_file = None
    try:
        now = get_moscow_time()

        # 1) Create seller and buyer
        # Создаем или переиспользуем пользователей с уникальными telegram_id
        seller = db.query(User).filter(User.telegram_id == 900001).first()
        if not seller:
            seller = User(
                telegram_id=900001,
                username="seller_test",
                first_name="Продавец",
            )
            db.add(seller)
            db.commit()
            db.refresh(seller)

        buyer = db.query(User).filter(User.telegram_id == 900002).first()
        if not buyer:
            buyer = User(
                telegram_id=900002,
                username="buyer_test",
                first_name="Покупатель",
            )
            db.add(buyer)
            db.commit()
            db.refresh(buyer)

        # 2) Create lot ended in the past
        lot = Lot(
            title="Тестовый лот для документа",
            description="Описание тестового лота",
            starting_price=1000.0,
            current_price=1000.0,
            min_bid_increment=10.0,
            seller_id=seller.id,
            status=LotStatus.ACTIVE,
            document_type=DocumentType.STANDARD,
            start_time=now - timedelta(hours=1),
            end_time=now - timedelta(minutes=1),
        )
        db.add(lot)
        db.commit()
        db.refresh(lot)

        # 3) Place a bid from buyer and update current price
        bid_amount = 1337.0
        db.add(
            Bid(lot_id=lot.id, bidder_id=buyer.id, amount=bid_amount, is_auto_bid=False)
        )
        lot.current_price = bid_amount
        db.commit()

        # 4) Generate document for winner
        document = create_document(lot, buyer)
        tmp_dir = Path("tmp_docs_test")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_file = tmp_dir / f"transfer_lot_{lot.id}_buyer_{buyer.id}.txt"
        assert save_document_to_file(
            document, str(tmp_file)
        ), "Не удалось сохранить документ"

        # 5) Validate content
        content = Path(tmp_file).read_text(encoding="utf-8")
        errors = []
        if "Тестовый лот для документа" not in content:
            errors.append("Название лота отсутствует в документе")
        if "Описание тестового лота" not in content:
            errors.append("Описание лота отсутствует в документе")
        if (
            f"{bid_amount:,.2f}".replace(",", " ") not in content
            and f"{bid_amount:,.2f}" not in content
        ):
            errors.append("Финальная цена отсутствует или неверно отформатирована")
        if "Продавец" not in content:
            errors.append("Данные продавца отсутствуют")
        if "Покупатель" not in content:
            errors.append("Данные покупателя отсутствуют")
        if "DOC-" not in content:
            errors.append("Номер документа (DOC-...) отсутствует")

        if errors:
            print("E2E Document Test: FAIL")
            for e in errors:
                print(" -", e)
            sys.exit(1)
        else:
            print("E2E Document Test: PASS")
            print(f"Документ: {tmp_file}")
            sys.exit(0)
    except Exception as e:
        print("E2E Document Test: EXCEPTION", e)
        sys.exit(2)
    finally:
        # Cleanup temp file
        try:
            if tmp_file and Path(tmp_file).exists():
                os.remove(tmp_file)
        except Exception:
            pass
        # Note: оставляем записи в БД для трассировки при необходимости
        db.close()


if __name__ == "__main__":
    run()
