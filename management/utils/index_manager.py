"""
Менеджер индексов для оптимизации базы данных
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import Index, inspect, text
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateIndex, DropIndex

from database.db import get_db_session
from database.models import Base, Bid, Complaint, Lot, Payment, User

logger = logging.getLogger(__name__)


class IndexManager:
    """Менеджер индексов для оптимизации БД"""

    def __init__(self):
        self.recommended_indexes = {
            "lots": [
                {
                    "name": "idx_lots_status_end_time",
                    "columns": ["status", "end_time"],
                    "description": "Индекс для быстрого поиска активных лотов по времени окончания",
                },
                {
                    "name": "idx_lots_document_type_status",
                    "columns": ["document_type", "status"],
                    "description": "Индекс для поиска лотов по типу документа и статусу",
                },
                {
                    "name": "idx_lots_seller_status",
                    "columns": ["seller_id", "status"],
                    "description": "Индекс для быстрого получения лотов продавца",
                },
                {
                    "name": "idx_lots_created_at",
                    "columns": ["created_at"],
                    "description": "Индекс для сортировки по дате создания",
                },
            ],
            "bids": [
                {
                    "name": "idx_bids_lot_id_amount",
                    "columns": ["lot_id", "amount"],
                    "description": "Составной индекс для поиска ставок по лоту и сумме",
                },
                {
                    "name": "idx_bids_bidder_lot",
                    "columns": ["bidder_id", "lot_id"],
                    "description": "Индекс для поиска ставок пользователя по лоту",
                },
                {
                    "name": "idx_bids_created_at",
                    "columns": ["created_at"],
                    "description": "Индекс для сортировки ставок по времени",
                },
            ],
            "users": [
                {
                    "name": "idx_users_username",
                    "columns": ["username"],
                    "description": "Уникальный индекс для поиска по имени пользователя",
                },
                {
                    "name": "idx_users_telegram_id",
                    "columns": ["telegram_id"],
                    "description": "Уникальный индекс для поиска по Telegram ID",
                },
                {
                    "name": "idx_users_role",
                    "columns": ["role"],
                    "description": "Индекс для фильтрации по роли пользователя",
                },
            ],
            "complaints": [
                {
                    "name": "idx_complaints_status_created",
                    "columns": ["status", "created_at"],
                    "description": "Индекс для поиска жалоб по статусу и дате",
                },
                {
                    "name": "idx_complaints_lot_id",
                    "columns": ["lot_id"],
                    "description": "Индекс для поиска жалоб по лоту",
                },
            ],
            "payments": [
                {
                    "name": "idx_payments_user_status",
                    "columns": ["user_id", "status"],
                    "description": "Индекс для поиска платежей пользователя по статусу",
                },
                {
                    "name": "idx_payments_created_at",
                    "columns": ["created_at"],
                    "description": "Индекс для сортировки платежей по времени",
                },
            ],
        }

    def get_existing_indexes(self, table_name: str) -> List[Dict[str, Any]]:
        """Получает существующие индексы для таблицы"""
        try:
            with get_db_session() as db:
                # Получаем информацию об индексах
                inspector = inspect(db.bind)
                indexes = inspector.get_indexes(table_name)

                result = []
                for index in indexes:
                    result.append(
                        {
                            "name": index.get("name"),
                            "columns": index.get("column_names", []),
                            "unique": index.get("unique", False),
                            "description": f"Индекс на колонках: {', '.join(index.get('column_names', []))}",
                        }
                    )

                return result

        except Exception as e:
            logger.error(f"Ошибка при получении индексов для таблицы {table_name}: {e}")
            return []

    def get_all_existing_indexes(self) -> Dict[str, List[Dict[str, Any]]]:
        """Получает все существующие индексы"""
        try:
            with get_db_session() as db:
                inspector = inspect(db.bind)
                table_names = inspector.get_table_names()

                all_indexes = {}
                for table_name in table_names:
                    all_indexes[table_name] = self.get_existing_indexes(table_name)

                return all_indexes

        except Exception as e:
            logger.error(f"Ошибка при получении всех индексов: {e}")
            return {}

    def create_index(
        self, table_name: str, index_name: str, columns: List[str], unique: bool = False
    ) -> bool:
        """Создает индекс"""
        try:
            with get_db_session() as db:
                # Создаем SQL для создания индекса
                columns_str = ", ".join(columns)
                unique_str = "UNIQUE" if unique else ""

                sql = f"CREATE {unique_str} INDEX {index_name} ON {table_name} ({columns_str})"

                # Выполняем SQL
                db.execute(text(sql))
                db.commit()

                logger.info(f"Создан индекс {index_name} для таблицы {table_name}")
                return True

        except Exception as e:
            logger.error(f"Ошибка при создании индекса {index_name}: {e}")
            return False

    def drop_index(self, table_name: str, index_name: str) -> bool:
        """Удаляет индекс"""
        try:
            with get_db_session() as db:
                # Создаем SQL для удаления индекса
                sql = f"DROP INDEX {index_name}"

                # Выполняем SQL
                db.execute(text(sql))
                db.commit()

                logger.info(f"Удален индекс {index_name} для таблицы {table_name}")
                return True

        except Exception as e:
            logger.error(f"Ошибка при удалении индекса {index_name}: {e}")
            return False

    def create_recommended_indexes(
        self, table_name: Optional[str] = None
    ) -> Dict[str, bool]:
        """Создает рекомендуемые индексы"""
        results = {}

        try:
            tables_to_process = (
                [table_name] if table_name else self.recommended_indexes.keys()
            )

            for table in tables_to_process:
                if table not in self.recommended_indexes:
                    continue

                table_results = {}
                for index_info in self.recommended_indexes[table]:
                    # Проверяем, существует ли уже индекс
                    existing_indexes = self.get_existing_indexes(table)
                    index_exists = any(
                        idx["name"] == index_info["name"] for idx in existing_indexes
                    )

                    if not index_exists:
                        # Создаем индекс
                        success = self.create_index(
                            table, index_info["name"], index_info["columns"]
                        )
                        table_results[index_info["name"]] = success
                    else:
                        table_results[index_info["name"]] = "already_exists"

                results[table] = table_results

            return results

        except Exception as e:
            logger.error(f"Ошибка при создании рекомендуемых индексов: {e}")
            return {}

    def analyze_table_performance(self, table_name: str) -> Dict[str, Any]:
        """Анализирует производительность таблицы"""
        try:
            with get_db_session() as db:
                # Получаем статистику таблицы в зависимости от типа
                if table_name == "lots":
                    stats_sql = f"""
                    SELECT 
                        COUNT(*) as total_rows,
                        SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active_rows,
                        AVG(CASE WHEN status = 'active' THEN 1 ELSE 0 END) * 100 as active_percentage
                    FROM {table_name}
                    """
                elif table_name == "users":
                    stats_sql = f"""
                    SELECT 
                        COUNT(*) as total_rows,
                        SUM(CASE WHEN is_banned = 0 THEN 1 ELSE 0 END) as active_rows,
                        AVG(CASE WHEN is_banned = 0 THEN 1 ELSE 0 END) * 100 as active_percentage
                    FROM {table_name}
                    """
                elif table_name == "bids":
                    stats_sql = f"""
                    SELECT 
                        COUNT(*) as total_rows,
                        COUNT(*) as active_rows,
                        100.0 as active_percentage
                    FROM {table_name}
                    """
                elif table_name == "complaints":
                    stats_sql = f"""
                    SELECT 
                        COUNT(*) as total_rows,
                        SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as active_rows,
                        AVG(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) * 100 as active_percentage
                    FROM {table_name}
                    """
                elif table_name == "payments":
                    stats_sql = f"""
                    SELECT 
                        COUNT(*) as total_rows,
                        SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as active_rows,
                        AVG(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) * 100 as active_percentage
                    FROM {table_name}
                    """
                else:
                    # Для неизвестных таблиц используем простой подсчет
                    stats_sql = f"""
                    SELECT 
                        COUNT(*) as total_rows,
                        COUNT(*) as active_rows,
                        100.0 as active_percentage
                    FROM {table_name}
                    """

                result = db.execute(text(stats_sql)).fetchone()

                # Получаем информацию об индексах
                indexes = self.get_existing_indexes(table_name)

                # Анализируем рекомендации
                recommendations = []
                if table_name in self.recommended_indexes:
                    existing_names = {idx["name"] for idx in indexes}
                    for rec_index in self.recommended_indexes[table_name]:
                        if rec_index["name"] not in existing_names:
                            recommendations.append(
                                {
                                    "name": rec_index["name"],
                                    "columns": rec_index["columns"],
                                    "description": rec_index["description"],
                                    "priority": (
                                        "high"
                                        if "status" in rec_index["columns"]
                                        else "medium"
                                    ),
                                }
                            )

                return {
                    "table_name": table_name,
                    "total_rows": result[0] if result else 0,
                    "active_rows": result[1] if result else 0,
                    "active_percentage": result[2] if result else 0,
                    "existing_indexes": indexes,
                    "recommendations": recommendations,
                    "index_coverage": len(indexes)
                    / max(len(self.recommended_indexes.get(table_name, [])), 1)
                    * 100,
                }

        except Exception as e:
            logger.error(
                f"Ошибка при анализе производительности таблицы {table_name}: {e}"
            )
            return {}

    def get_performance_report(self) -> Dict[str, Any]:
        """Получает общий отчет о производительности индексов"""
        try:
            all_tables = list(self.recommended_indexes.keys())
            table_analyses = {}
            total_recommendations = 0
            total_existing = 0

            for table_name in all_tables:
                analysis = self.analyze_table_performance(table_name)
                table_analyses[table_name] = analysis

                total_existing += len(analysis.get("existing_indexes", []))
                total_recommendations += len(analysis.get("recommendations", []))

            return {
                "total_tables": len(all_tables),
                "total_existing_indexes": total_existing,
                "total_recommendations": total_recommendations,
                "overall_coverage": (
                    total_existing / max(total_existing + total_recommendations, 1)
                )
                * 100,
                "table_analyses": table_analyses,
                "priority_recommendations": self._get_priority_recommendations(
                    table_analyses
                ),
            }

        except Exception as e:
            logger.error(f"Ошибка при получении отчета о производительности: {e}")
            return {}

    def _get_priority_recommendations(
        self, table_analyses: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Получает приоритетные рекомендации по индексам"""
        recommendations = []

        try:
            for table_name, analysis in table_analyses.items():
                for rec in analysis.get("recommendations", []):
                    if rec.get("priority") == "high":
                        recommendations.append(
                            {
                                "table": table_name,
                                "index_name": rec["name"],
                                "columns": rec["columns"],
                                "description": rec["description"],
                                "priority": rec["priority"],
                            }
                        )

            # Сортируем по приоритету
            recommendations.sort(key=lambda x: x["priority"] == "high", reverse=True)

            return recommendations[:10]  # Топ 10 рекомендаций

        except Exception as e:
            logger.error(f"Ошибка при получении приоритетных рекомендаций: {e}")
            return []

    def optimize_table_queries(self, table_name: str) -> bool:
        """Оптимизирует запросы к таблице"""
        try:
            # Создаем рекомендуемые индексы
            results = self.create_recommended_indexes(table_name)

            if table_name in results:
                success_count = sum(
                    1 for result in results[table_name].values() if result is True
                )

                logger.info(
                    f"Оптимизирована таблица {table_name}: создано {success_count} индексов"
                )
                return success_count > 0

            return False

        except Exception as e:
            logger.error(f"Ошибка при оптимизации таблицы {table_name}: {e}")
            return False

    def get_index_usage_stats(self) -> Dict[str, Any]:
        """Получает статистику использования индексов"""
        try:
            with get_db_session() as db:
                # SQLite не предоставляет детальную статистику использования индексов
                # Возвращаем базовую информацию
                return {
                    "message": "SQLite не предоставляет детальную статистику использования индексов",
                    "total_indexes": sum(
                        len(self.get_existing_indexes(table))
                        for table in self.recommended_indexes.keys()
                    ),
                    "recommended_indexes": sum(
                        len(indexes) for indexes in self.recommended_indexes.values()
                    ),
                }

        except Exception as e:
            logger.error(f"Ошибка при получении статистики использования индексов: {e}")
            return {}


# Глобальный экземпляр менеджера индексов
index_manager = IndexManager()


def create_recommended_indexes(table_name: Optional[str] = None) -> Dict[str, bool]:
    """Создает рекомендуемые индексы"""
    return index_manager.create_recommended_indexes(table_name)


def analyze_table_performance(table_name: str) -> Dict[str, Any]:
    """Анализирует производительность таблицы"""
    return index_manager.analyze_table_performance(table_name)


def get_index_performance_report() -> Dict[str, Any]:
    """Получает отчет о производительности индексов"""
    return index_manager.get_performance_report()


def optimize_all_tables() -> Dict[str, bool]:
    """Оптимизирует все таблицы"""
    results = {}

    for table_name in index_manager.recommended_indexes.keys():
        results[table_name] = index_manager.optimize_table_queries(table_name)

    return results
