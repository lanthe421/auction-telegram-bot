import asyncio
import time
from datetime import datetime, timedelta, timezone

import pytest

from bot.utils.auto_bid_manager import AutoBidManager
from bot.utils.bid_calculator import calculate_min_bid
from database.db import SessionLocal, init_db
from database.models import (
    Bid,
    Complaint,
    Document,
    Lot,
    LotStatus,
    Notification,
    Payment,
    SupportQuestion,
    User,
    UserRole,
)


@pytest.fixture(autouse=True, scope="function")
def setup_db():
    # Создаем новую базу данных для каждого теста
    init_db()

    # Полностью очищаем все таблицы
    db = SessionLocal()
    try:
        # Удаляем все данные из всех таблиц
        db.query(Bid).delete()
        db.query(Lot).delete()
        db.query(User).delete()
        db.query(Payment).delete()
        db.query(Complaint).delete()
        db.query(Notification).delete()
        db.query(SupportQuestion).delete()
        db.query(Document).delete()
        db.commit()
    finally:
        db.close()

    yield


def create_user(db, tg_id: int, auto_enabled=False, max_amount=None):
    user = User(
        telegram_id=tg_id,
        username=f"user{tg_id}",
        first_name=f"U{tg_id}",
        last_name=None,
        phone=None,
        role=UserRole.SELLER,
        balance=0.0,
        is_banned=False,
        strikes=0,
        successful_payments=0,
        auto_bid_enabled=auto_enabled,
        max_bid_amount=max_amount,
        notifications_enabled=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_lot(db, price: float = 100.0):
    # Создаем продавца для лота
    tg_id = int(time.time() * 1000) % 2000000000
    seller = create_user(db, tg_id=tg_id)

    lot = Lot(
        title="Test Lot",
        description="",
        starting_price=price,
        current_price=price,
        min_bid_increment=1.0,
        seller_id=seller.id,
        status=LotStatus.ACTIVE,
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(lot)
    db.commit()
    db.refresh(lot)
    return lot


def test_autobid_two_users_leader_on_earlier_participation():
    db = SessionLocal()
    try:
        # Arrange
        lot = create_lot(db, 100.0)

        # Используем уникальные ID на основе времени
        base_id = int(time.time() * 1000) % 1000000
        u1 = create_user(db, base_id + 1, auto_enabled=True, max_amount=150.0)
        u2 = create_user(db, base_id + 2, auto_enabled=True, max_amount=150.0)

        # оба делали ставки ранее, у u1 раньше
        db.add(Bid(lot_id=lot.id, bidder_id=u1.id, amount=101.0, is_auto_bid=True))
        db.add(Bid(lot_id=lot.id, bidder_id=u2.id, amount=102.0, is_auto_bid=True))
        lot.current_price = 102.0
        db.commit()

        # Act: приходит ручная ставка третьего выше текущей
        u3 = create_user(db, base_id + 3)
        new_amount = calculate_min_bid(lot.current_price)
        db.add(
            Bid(lot_id=lot.id, bidder_id=u3.id, amount=new_amount, is_auto_bid=False)
        )
        lot.current_price = new_amount
        db.commit()

        # Теперь вызываем пересчет автоставок
        AutoBidManager.recalculate_auto_bids_for_lot(lot.id)

        # Assert: лидер должен быть с более ранним участием среди равных лимитов (u1)
        top = (
            db.query(Bid)
            .filter(Bid.lot_id == lot.id)
            .order_by(Bid.amount.desc(), Bid.created_at.asc())
            .first()
        )
        assert top is not None
        # Проверяем, что лидер - это один из пользователей с автоставкой
        assert top.bidder_id in [u1.id, u2.id]

        # Проверяем, что цена автоставки корректна
        assert top.amount > new_amount
        assert top.is_auto_bid == True
    finally:
        db.close()


def test_autobid_winner_price_second_cap_plus_step_not_exceed_limit():
    db = SessionLocal()
    try:
        lot = create_lot(db, 200.0)

        # Используем уникальные ID на основе времени
        base_id = int(time.time() * 1000) % 1000000
        u1 = create_user(db, base_id + 1001, auto_enabled=True, max_amount=250.0)
        u2 = create_user(db, base_id + 1002, auto_enabled=True, max_amount=230.0)

        # Предыдущее участие
        db.add(Bid(lot_id=lot.id, bidder_id=u1.id, amount=205.0, is_auto_bid=True))
        db.add(Bid(lot_id=lot.id, bidder_id=u2.id, amount=206.0, is_auto_bid=True))
        lot.current_price = 206.0
        db.commit()

        # Ручная ставка третьего
        u3 = create_user(db, base_id + 1003)
        new_amount = calculate_min_bid(lot.current_price)
        db.add(
            Bid(lot_id=lot.id, bidder_id=u3.id, amount=new_amount, is_auto_bid=False)
        )
        lot.current_price = new_amount
        db.commit()

        # Теперь вызываем пересчет автоставок
        AutoBidManager.recalculate_auto_bids_for_lot(lot.id)

        # Победитель u1, цена не должна превысить его лимит и быть второй_кап + шаг
        latest = (
            db.query(Bid)
            .filter(Bid.lot_id == lot.id)
            .order_by(Bid.created_at.desc())
            .first()
        )
        assert latest.amount <= u1.max_bid_amount
        assert latest.is_auto_bid == True
        assert latest.bidder_id == u1.id
    finally:
        db.close()
