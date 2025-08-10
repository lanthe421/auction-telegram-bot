"""
Репозиторий для работы с лотами
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, func, or_
from sqlalchemy.orm import Session, joinedload

from database.models import Bid, Lot, LotStatus, User
from management.utils.cache_manager import cache_manager, cache_result
from management.utils.performance_monitor import performance_monitor

logger = logging.getLogger(__name__)


class LotRepository:
    """Репозиторий для работы с лотами"""

    def __init__(self, db: Session):
        self.db = db

    @cache_result(ttl=300, cache_name="lots")  # 5 минут
    def get_lot_by_id(self, lot_id: int) -> Optional[Lot]:
        """Получает лот по ID с кэшированием"""
        start_time = datetime.now()
        try:
            lot = (
                self.db.query(Lot)
                .options(joinedload(Lot.seller))
                .filter(Lot.id == lot_id)
                .first()
            )

            # Записываем метрики производительности
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            performance_monitor.record_database_query(execution_time)

            return lot
        except Exception as e:
            logger.error(f"Ошибка при получении лота {lot_id}: {e}")
            return None

    @cache_result(ttl=180, cache_name="lots")  # 3 минуты
    def get_active_lots(self, limit: int = 50, offset: int = 0) -> List[Lot]:
        """Получает активные лоты с кэшированием"""
        start_time = datetime.now()
        try:
            lots = (
                self.db.query(Lot)
                .options(joinedload(Lot.seller))
                .filter(Lot.status == LotStatus.ACTIVE)
                .filter(Lot.end_time > datetime.now())
                .order_by(desc(Lot.created_at))
                .limit(limit)
                .offset(offset)
                .all()
            )

            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            performance_monitor.record_database_query(execution_time)

            return lots
        except Exception as e:
            logger.error(f"Ошибка при получении активных лотов: {e}")
            return []

    @cache_result(ttl=600, cache_name="lots")  # 10 минут
    def get_lots_by_category(self, category: str, limit: int = 50) -> List[Lot]:
        """Получает лоты по категории с кэшированием"""
        start_time = datetime.now()
        try:
            lots = (
                self.db.query(Lot)
                .options(joinedload(Lot.seller))
                .filter(Lot.category == category)
                .filter(Lot.status == LotStatus.ACTIVE)
                .filter(Lot.end_time > datetime.now())
                .order_by(desc(Lot.created_at))
                .limit(limit)
                .all()
            )

            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            performance_monitor.record_database_query(execution_time)

            return lots
        except Exception as e:
            logger.error(f"Ошибка при получении лотов по категории {category}: {e}")
            return []

    def search_lots(self, query: str, limit: int = 50) -> List[Lot]:
        """Поиск лотов по тексту (без кэширования для динамичности)"""
        start_time = datetime.now()
        try:
            search_term = f"%{query}%"
            lots = (
                self.db.query(Lot)
                .options(joinedload(Lot.seller))
                .filter(
                    and_(
                        Lot.status == LotStatus.ACTIVE,
                        Lot.end_time > datetime.now(),
                        or_(
                            Lot.title.ilike(search_term),
                            Lot.description.ilike(search_term),
                            Lot.category.ilike(search_term),
                        ),
                    )
                )
                .order_by(desc(Lot.created_at))
                .limit(limit)
                .all()
            )

            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            performance_monitor.record_database_query(execution_time)

            return lots
        except Exception as e:
            logger.error(f"Ошибка при поиске лотов: {e}")
            return []

    def get_user_lots(
        self, user_id: int, status: Optional[LotStatus] = None
    ) -> List[Lot]:
        """Получает лоты пользователя"""
        start_time = datetime.now()
        try:
            query = self.db.query(Lot).filter(Lot.seller_id == user_id)

            if status:
                query = query.filter(Lot.status == status)

            lots = query.order_by(desc(Lot.created_at)).all()

            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            performance_monitor.record_database_query(execution_time)

            return lots
        except Exception as e:
            logger.error(f"Ошибка при получении лотов пользователя {user_id}: {e}")
            return []

    def get_ending_soon_lots(self, hours: int = 24) -> List[Lot]:
        """Получает лоты, которые скоро закончатся"""
        start_time = datetime.now()
        try:
            end_time = datetime.now() + timedelta(hours=hours)
            lots = (
                self.db.query(Lot)
                .options(joinedload(Lot.seller))
                .filter(
                    and_(
                        Lot.status == LotStatus.ACTIVE,
                        Lot.end_time <= end_time,
                        Lot.end_time > datetime.now(),
                    )
                )
                .order_by(Lot.end_time)
                .all()
            )

            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            performance_monitor.record_database_query(execution_time)

            return lots
        except Exception as e:
            logger.error(f"Ошибка при получении лотов, заканчивающихся скоро: {e}")
            return []

    def get_lot_statistics(self) -> Dict[str, Any]:
        """Получает статистику по лотам"""
        start_time = datetime.now()
        try:
            stats = {
                "total_lots": self.db.query(func.count(Lot.id)).scalar(),
                "active_lots": self.db.query(func.count(Lot.id))
                .filter(Lot.status == LotStatus.ACTIVE)
                .scalar(),
                "sold_lots": self.db.query(func.count(Lot.id))
                .filter(Lot.status == LotStatus.SOLD)
                .scalar(),
                "cancelled_lots": self.db.query(func.count(Lot.id))
                .filter(Lot.status == LotStatus.CANCELLED)
                .scalar(),
                "total_value": self.db.query(func.sum(Lot.starting_price))
                .filter(Lot.status == LotStatus.SOLD)
                .scalar()
                or 0,
            }

            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            performance_monitor.record_database_query(execution_time)

            return stats
        except Exception as e:
            logger.error(f"Ошибка при получении статистики лотов: {e}")
            return {}

    def create_lot(self, lot_data: Dict[str, Any]) -> Optional[Lot]:
        """Создает новый лот"""
        try:
            lot = Lot(**lot_data)
            self.db.add(lot)
            self.db.commit()
            self.db.refresh(lot)

            # Инвалидируем кэш
            cache_manager.invalidate_cache_pattern("lots", "lots")

            logger.info(f"Создан новый лот: {lot.id}")
            return lot
        except Exception as e:
            logger.error(f"Ошибка при создании лота: {e}")
            self.db.rollback()
            return None

    def update_lot(self, lot_id: int, update_data: Dict[str, Any]) -> bool:
        """Обновляет лот"""
        try:
            lot = self.db.query(Lot).filter(Lot.id == lot_id).first()
            if not lot:
                return False

            for key, value in update_data.items():
                if hasattr(lot, key):
                    setattr(lot, key, value)

            self.db.commit()

            # Инвалидируем кэш
            cache_manager.invalidate_cache_pattern("lots", "lots")

            logger.info(f"Лот {lot_id} обновлен")
            return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении лота {lot_id}: {e}")
            self.db.rollback()
            return False

    def delete_lot(self, lot_id: int) -> bool:
        """Удаляет лот"""
        try:
            lot = self.db.query(Lot).filter(Lot.id == lot_id).first()
            if not lot:
                return False

            self.db.delete(lot)
            self.db.commit()

            # Инвалидируем кэш
            cache_manager.invalidate_cache_pattern("lots", "lots")

            logger.info(f"Лот {lot_id} удален")
            return True
        except Exception as e:
            logger.error(f"Ошибка при удалении лота {lot_id}: {e}")
            self.db.rollback()
            return False

    def get_lot_with_bids(self, lot_id: int) -> Optional[Lot]:
        """Получает лот со всеми ставками"""
        start_time = datetime.now()
        try:
            lot = (
                self.db.query(Lot)
                .options(
                    joinedload(Lot.seller), joinedload(Lot.bids).joinedload(Bid.bidder)
                )
                .filter(Lot.id == lot_id)
                .first()
            )

            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            performance_monitor.record_database_query(execution_time)

            return lot
        except Exception as e:
            logger.error(f"Ошибка при получении лота {lot_id} со ставками: {e}")
            return None
