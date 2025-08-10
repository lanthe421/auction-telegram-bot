import sys
from pathlib import Path

sys.path.append(str(Path(".").resolve()))

from bot.utils.documents import create_document, save_document_to_file
from database.db import SessionLocal
from database.models import DocumentType, Lot, User


def show_document_example():
    db = SessionLocal()
    try:
        # Get existing test users
        seller = db.query(User).filter(User.telegram_id == 900001).first()
        buyer = db.query(User).filter(User.telegram_id == 900002).first()

        if not seller or not buyer:
            print("Test users not found. Run e2e test first.")
            return

        # Create a test lot
        lot = Lot(
            title="iPhone 15 Pro Max 256GB",
            description="Новый iPhone 15 Pro Max в оригинальной упаковке, цвет Natural Titanium",
            starting_price=120000.0,
            current_price=135000.0,
            min_bid_increment=1000.0,
            seller_id=seller.id,
            document_type=DocumentType.STANDARD,
        )

        db.add(lot)
        db.commit()
        db.refresh(lot)

        # Generate document
        document = create_document(lot, buyer)

        # Save to file
        tmp_file = "example_document.txt"
        if save_document_to_file(document, tmp_file):
            print("=== ПРИМЕР ДОКУМЕНТА ===\n")
            with open(tmp_file, "r", encoding="utf-8") as f:
                print(f.read())

            # Cleanup
            Path(tmp_file).unlink(missing_ok=True)
        else:
            print("Failed to save document")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    show_document_example()
