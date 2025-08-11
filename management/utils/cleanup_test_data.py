"""
Утилита для безопасной очистки тестовых данных (пользователи/лоты/ставки),
созданных автоматическими e2e-тестами или в процессе разработки.

Критерии отбора тестовых записей максимально консервативны:
- Пользователи: username начинается с "user" и first_name начинается с "U";
  дополнительно не должно быть платежей (чтобы не затронуть живые аккаунты).
- Лоты: известные тестовые заголовки ("Test Lot", "Тестовый лот для документа").

Скрипт поддерживает dry-run режим по умолчанию: только показывает, что будет удалено.
"""

from __future__ import annotations

import logging
from typing import Iterable, List, Tuple

from sqlalchemy.orm import Session

from database.db import SessionLocal
from database.models import AutoBid, Bid, Document, Lot, Payment, User

logger = logging.getLogger(__name__)


TEST_LOT_TITLES = {"Test Lot", "Тестовый лот для документа"}


def _find_test_users(db: Session) -> List[User]:
    # user.username like 'user%' и first_name like 'U%'; без платежей — минимальный риск
    candidates = (
        db.query(User)
        .filter(User.username.isnot(None))
        .filter(User.first_name.isnot(None))
        .filter(User.username.like("user%"))
        .filter(User.first_name.like("U%"))
        .all()
    )

    safe: List[User] = []
    for u in candidates:
        # Пользователь без завершенных/любых платежей — безопаснее удалять как тестового
        has_payments = (
            db.query(Payment).filter(Payment.user_id == u.id).first() is not None
        )
        if not has_payments:
            safe.append(u)
    return safe


def _find_test_lots(db: Session) -> List[Lot]:
    return db.query(Lot).filter(Lot.title.in_(TEST_LOT_TITLES)).all()


def _delete_user_with_relations(db: Session, user: User) -> Tuple[int, int, int]:
    """Удаляет пользователя и связанные сущности. Возвращает (auto_bids, bids, users) счётчики."""
    auto_bids_deleted = (
        db.query(AutoBid)
        .filter(AutoBid.user_id == user.id)
        .delete(synchronize_session=False)
    )
    bids_deleted = (
        db.query(Bid).filter(Bid.bidder_id == user.id).delete(synchronize_session=False)
    )
    users_deleted = (
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
    )
    return auto_bids_deleted, bids_deleted, users_deleted


def _delete_lot_with_relations(db: Session, lot: Lot) -> Tuple[int, int, int, int]:
    """Удаляет лот и связанные сущности. Возвращает (auto_bids, bids, documents, lots)."""
    auto_bids_deleted = (
        db.query(AutoBid)
        .filter(AutoBid.lot_id == lot.id)
        .delete(synchronize_session=False)
    )
    bids_deleted = (
        db.query(Bid).filter(Bid.lot_id == lot.id).delete(synchronize_session=False)
    )
    docs_deleted = (
        db.query(Document)
        .filter(Document.lot_id == lot.id)
        .delete(synchronize_session=False)
    )
    lots_deleted = (
        db.query(Lot).filter(Lot.id == lot.id).delete(synchronize_session=False)
    )
    return auto_bids_deleted, bids_deleted, docs_deleted, lots_deleted


def _cleanup_orphans(db: Session) -> Tuple[int, int]:
    """Удаляет осиротевшие записи AutoBid/Bid, у которых нет соответствующих User/Lot."""
    # Для SQLite проще выполнить через подзапросы с NOT IN
    user_ids = [u.id for u in db.query(User.id).all()]
    lot_ids = [l.id for l in db.query(Lot.id).all()]

    auto_deleted = (
        db.query(AutoBid)
        .filter(~AutoBid.user_id.in_(user_ids) | ~AutoBid.lot_id.in_(lot_ids))
        .delete(synchronize_session=False)
    )
    bids_deleted = (
        db.query(Bid)
        .filter(~Bid.bidder_id.in_(user_ids) | ~Bid.lot_id.in_(lot_ids))
        .delete(synchronize_session=False)
    )
    return auto_deleted, bids_deleted


def run_cleanup(*, dry_run: bool = True) -> dict:
    db = SessionLocal()
    report = {
        "dry_run": dry_run,
        "test_users": 0,
        "test_lots": 0,
        "deleted": {
            "users": 0,
            "bids": 0,
            "auto_bids": 0,
            "documents": 0,
            "lots": 0,
            "orphans_auto_bids": 0,
            "orphans_bids": 0,
        },
    }

    try:
        test_users = _find_test_users(db)
        test_lots = _find_test_lots(db)
        report["test_users"] = len(test_users)
        report["test_lots"] = len(test_lots)

        logger.info(
            f"Найдено тестовых пользователей: {len(test_users)}, тестовых лотов: {len(test_lots)}"
        )

        if dry_run:
            return report

        # Удаляем тестовые лоты (и связи)
        for lot in test_lots:
            a, b, d, l = _delete_lot_with_relations(db, lot)
            report["deleted"]["auto_bids"] += a
            report["deleted"]["bids"] += b
            report["deleted"]["documents"] += d
            report["deleted"]["lots"] += l

        # Удаляем тестовых пользователей (и связи)
        for user in test_users:
            a, b, u = _delete_user_with_relations(db, user)
            report["deleted"]["auto_bids"] += a
            report["deleted"]["bids"] += b
            report["deleted"]["users"] += u

        # Чистим осиротевшие записи
        oa, ob = _cleanup_orphans(db)
        report["deleted"]["orphans_auto_bids"] = oa
        report["deleted"]["orphans_bids"] = ob

        db.commit()

        logger.info(f"Очистка завершена: {report}")
        return report
    except Exception as e:
        db.rollback()
        logger.error(f"Ошибка при очистке тестовых данных: {e}")
        raise
    finally:
        db.close()
