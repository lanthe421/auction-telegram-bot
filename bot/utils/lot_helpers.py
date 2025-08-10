from typing import Optional, Tuple

from database.db import SessionLocal
from database.models import Bid, Lot, User


def mask_username(username: Optional[str]) -> str:
    if not username:
        return "—"
    # Показываем первые 3 символа username, остальное маскируем
    prefix = username[:3]
    return f"@{prefix}**"


def get_current_leader(db: SessionLocal, lot_id: int) -> Tuple[str, Optional[float]]:
    """Возвращает маскированного лидера и его сумму или ("—", None), если ставок нет.

    Убраны "фильтры свежести", чтобы избежать проблем с наивными/часовыми зонами.
    Берём просто максимальную ставку по лоту (и самую новую при равенстве).
    """

    lot: Optional[Lot] = db.query(Lot).filter(Lot.id == lot_id).first()
    if not lot:
        return "—", None

    # Берём ставку с наибольшей суммой (и самой новой при равенстве)
    top_bid: Optional[Bid] = (
        db.query(Bid)
        .filter(Bid.lot_id == lot_id)
        .order_by(Bid.amount.desc(), Bid.created_at.desc())
        .first()
    )

    if not top_bid:
        return "—", None

    user = db.query(User).filter(User.id == top_bid.bidder_id).first()
    if not user:
        return "—", float(top_bid.amount)

    # Предпочитаем username. Если его нет — маскируем имя. Если нет имени — показываем "—"
    if user.username:
        masked = mask_username(user.username)
    elif user.first_name:
        prefix = user.first_name[:3]
        masked = f"{prefix}**"
    else:
        # Если нет ни username, ни имени, показываем "—"
        masked = "—"

    return masked, float(top_bid.amount)


def _fresh_bids_query(db: SessionLocal, lot: Lot):
    """Возвращает запрос по ставкам лота, отфильтрованный по времени старта/создания."""
    q = db.query(Bid).filter(Bid.lot_id == lot.id)
    # Убираем временной фильтр, так как он блокирует ставки, созданные до старта лота
    # threshold = lot.start_time or lot.created_at
    # if threshold is not None:
    #     q = q.filter(Bid.created_at >= threshold)
    return q


def get_fresh_bids_count(db: SessionLocal, lot_id: int) -> int:
    lot = db.query(Lot).filter(Lot.id == lot_id).first()
    if not lot:
        return 0
    return _fresh_bids_query(db, lot).count()


def get_highest_fresh_bid_amount(db: SessionLocal, lot_id: int) -> Optional[float]:
    lot = db.query(Lot).filter(Lot.id == lot_id).first()
    if not lot:
        return None
    bid = _fresh_bids_query(db, lot).order_by(Bid.amount.desc()).first()
    return float(bid.amount) if bid else None
