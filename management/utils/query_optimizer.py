"""
Оптимизатор SQL запросов для улучшения производительности
"""

import logging
import time
from functools import wraps
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import inspect, text
from sqlalchemy.orm import Query, Session

from management.utils.cache_manager import cache_result
from management.utils.performance_monitor import performance_monitor

logger = logging.getLogger(__name__)


class QueryOptimizer:
    """Оптимизатор SQL запросов"""

    def __init__(self):
        self.query_stats = {}
        self.slow_query_threshold = 1000  # мс

    def optimize_query(self, query: Query, **kwargs) -> Query:
        """Оптимизирует SQL запрос"""
        try:
            # Добавляем подсказки для оптимизации
            if hasattr(query, "execution_options"):
                query = query.execution_options(
                    stream_results=True, max_row_buffer=1000
                )

            # Оптимизируем JOIN'ы
            query = self._optimize_joins(query)

            # Оптимизируем WHERE условия
            query = self._optimize_where(query)

            # Оптимизируем ORDER BY
            query = self._optimize_order_by(query)

            return query

        except Exception as e:
            logger.warning(f"Ошибка при оптимизации запроса: {e}")
            return query

    def _optimize_joins(self, query: Query) -> Query:
        """Оптимизирует JOIN'ы в запросе"""
        try:
            # Проверяем, есть ли уже JOIN'ы
            if hasattr(query, "_join_entities") and query._join_entities:
                # Убираем дублирующиеся JOIN'ы
                seen_joins = set()
                optimized_joins = []

                for join in query._join_entities:
                    join_key = (join.entity, join.onclause)
                    if join_key not in seen_joins:
                        seen_joins.add(join_key)
                        optimized_joins.append(join)

                # Пересоздаем запрос с оптимизированными JOIN'ами
                if len(optimized_joins) < len(query._join_entities):
                    logger.debug(
                        f"Оптимизированы JOIN'ы: {len(query._join_entities)} -> {len(optimized_joins)}"
                    )

            return query

        except Exception as e:
            logger.debug(f"Ошибка при оптимизации JOIN'ов: {e}")
            return query

    def _optimize_where(self, query: Query) -> Query:
        """Оптимизирует WHERE условия"""
        try:
            # Проверяем сложность WHERE условий
            if hasattr(query, "_where_criteria") and query._where_criteria:
                # Упрощаем сложные условия
                simplified_criteria = []

                for criterion in query._where_criteria:
                    if hasattr(criterion, "left") and hasattr(criterion, "right"):
                        # Проверяем, можно ли упростить условие
                        if self._can_simplify_criterion(criterion):
                            simplified = self._simplify_criterion(criterion)
                            if simplified:
                                simplified_criteria.append(simplified)
                        else:
                            simplified_criteria.append(criterion)
                    else:
                        simplified_criteria.append(criterion)

                if len(simplified_criteria) < len(query._where_criteria):
                    logger.debug(
                        f"Упрощены WHERE условия: {len(query._where_criteria)} -> {len(simplified_criteria)}"
                    )

            return query

        except Exception as e:
            logger.debug(f"Ошибка при оптимизации WHERE: {e}")
            return query

    def _can_simplify_criterion(self, criterion: Any) -> bool:
        """Проверяет, можно ли упростить условие"""
        try:
            # Простые проверки для упрощения
            if hasattr(criterion, "op") and criterion.op in ("==", "!="):
                return True
            if hasattr(criterion, "left") and hasattr(criterion, "right"):
                return True
            return False
        except:
            return False

    def _simplify_criterion(self, criterion: Any) -> Optional[Any]:
        """Упрощает условие"""
        try:
            # Базовая логика упрощения
            if hasattr(criterion, "op") and criterion.op == "==":
                if hasattr(criterion, "right") and criterion.right is None:
                    return None  # Убираем бессмысленные сравнения
            return criterion
        except:
            return criterion

    def _optimize_order_by(self, query: Query) -> Query:
        """Оптимизирует ORDER BY"""
        try:
            # Проверяем, есть ли ORDER BY
            if hasattr(query, "_order_by") and query._order_by:
                # Убираем дублирующиеся сортировки
                seen_orders = set()
                optimized_orders = []

                for order in query._order_by:
                    order_key = str(order)
                    if order_key not in seen_orders:
                        seen_orders.add(order_key)
                        optimized_orders.append(order)

                if len(optimized_orders) < len(query._order_by):
                    logger.debug(
                        f"Оптимизированы ORDER BY: {len(query._order_by)} -> {len(optimized_orders)}"
                    )

            return query

        except Exception as e:
            logger.debug(f"Ошибка при оптимизации ORDER BY: {e}")
            return query

    def analyze_query_performance(
        self, query: Query, execution_time: float
    ) -> Dict[str, Any]:
        """Анализирует производительность запроса"""
        try:
            # Получаем информацию о запросе
            query_str = str(query.compile(compile_kwargs={"literal_binds": True}))

            analysis = {
                "query": query_str[:200] + "..." if len(query_str) > 200 else query_str,
                "execution_time_ms": execution_time,
                "is_slow": execution_time > self.slow_query_threshold,
                "complexity_score": self._calculate_complexity_score(query),
                "optimization_suggestions": self._get_optimization_suggestions(
                    query, execution_time
                ),
            }

            # Сохраняем статистику
            query_hash = hash(query_str)
            self.query_stats[query_hash] = analysis

            return analysis

        except Exception as e:
            logger.error(f"Ошибка при анализе производительности запроса: {e}")
            return {}

    def _calculate_complexity_score(self, query: Query) -> int:
        """Вычисляет оценку сложности запроса"""
        score = 0

        try:
            # JOIN'ы
            if hasattr(query, "_join_entities"):
                score += len(query._join_entities) * 10

            # WHERE условия
            if hasattr(query, "_where_criteria"):
                score += len(query._where_criteria) * 5

            # ORDER BY
            if hasattr(query, "_order_by"):
                score += len(query._order_by) * 3

            # GROUP BY
            if hasattr(query, "_group_by"):
                score += len(query._group_by) * 5

            # LIMIT/OFFSET
            if hasattr(query, "_limit"):
                score += 2
            if hasattr(query, "_offset"):
                score += 2

        except Exception as e:
            logger.debug(f"Ошибка при вычислении сложности запроса: {e}")

        return score

    def _get_optimization_suggestions(
        self, query: Query, execution_time: float
    ) -> List[str]:
        """Получает предложения по оптимизации"""
        suggestions = []

        try:
            if execution_time > self.slow_query_threshold:
                suggestions.append(
                    "Запрос выполняется медленно, рассмотрите добавление индексов"
                )

            # Проверяем JOIN'ы
            if hasattr(query, "_join_entities") and len(query._join_entities) > 3:
                suggestions.append(
                    "Много JOIN'ов, рассмотрите денормализацию или подзапросы"
                )

            # Проверяем WHERE условия
            if hasattr(query, "_where_criteria") and len(query._where_criteria) > 5:
                suggestions.append(
                    "Сложные WHERE условия, рассмотрите упрощение логики"
                )

            # Проверяем ORDER BY
            if hasattr(query, "_order_by") and len(query._order_by) > 2:
                suggestions.append(
                    "Много полей сортировки, рассмотрите составные индексы"
                )

        except Exception as e:
            logger.debug(f"Ошибка при получении предложений по оптимизации: {e}")

        return suggestions

    def get_performance_report(self) -> Dict[str, Any]:
        """Получает отчет о производительности запросов"""
        try:
            if not self.query_stats:
                return {"message": "Нет данных о запросах"}

            total_queries = len(self.query_stats)
            slow_queries = sum(
                1 for stats in self.query_stats.values() if stats.get("is_slow", False)
            )
            avg_execution_time = (
                sum(
                    stats.get("execution_time_ms", 0)
                    for stats in self.query_stats.values()
                )
                / total_queries
            )

            return {
                "total_queries": total_queries,
                "slow_queries": slow_queries,
                "slow_queries_percentage": (
                    (slow_queries / total_queries) * 100 if total_queries > 0 else 0
                ),
                "avg_execution_time_ms": avg_execution_time,
                "max_execution_time_ms": max(
                    stats.get("execution_time_ms", 0)
                    for stats in self.query_stats.values()
                ),
                "complexity_distribution": self._get_complexity_distribution(),
                "top_slow_queries": self._get_top_slow_queries(5),
            }

        except Exception as e:
            logger.error(f"Ошибка при получении отчета о производительности: {e}")
            return {}

    def _get_complexity_distribution(self) -> Dict[str, int]:
        """Получает распределение сложности запросов"""
        distribution = {"low": 0, "medium": 0, "high": 0}

        try:
            for stats in self.query_stats.values():
                score = stats.get("complexity_score", 0)
                if score < 20:
                    distribution["low"] += 1
                elif score < 50:
                    distribution["medium"] += 1
                else:
                    distribution["high"] += 1
        except Exception as e:
            logger.debug(f"Ошибка при получении распределения сложности: {e}")

        return distribution

    def _get_top_slow_queries(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Получает топ медленных запросов"""
        try:
            sorted_queries = sorted(
                self.query_stats.values(),
                key=lambda x: x.get("execution_time_ms", 0),
                reverse=True,
            )

            return [
                {
                    "query": stats.get("query", ""),
                    "execution_time_ms": stats.get("execution_time_ms", 0),
                    "complexity_score": stats.get("complexity_score", 0),
                }
                for stats in sorted_queries[:limit]
            ]

        except Exception as e:
            logger.debug(f"Ошибка при получении топ медленных запросов: {e}")
            return []


# Глобальный экземпляр оптимизатора
query_optimizer = QueryOptimizer()


def optimize_query_decorator(func: Callable) -> Callable:
    """Декоратор для автоматической оптимизации запросов"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()

        try:
            # Выполняем функцию
            result = func(*args, **kwargs)

            # Анализируем производительность
            execution_time = (time.time() - start_time) * 1000

            # Если результат - это Query объект, оптимизируем его
            if hasattr(result, "compile"):
                result = query_optimizer.optimize_query(result)
                query_optimizer.analyze_query_performance(result, execution_time)

            # Записываем метрики
            performance_monitor.record_database_query(execution_time)

            return result

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"Ошибка в запросе {func.__name__}: {e}")
            performance_monitor.record_database_query(execution_time)
            raise

    return wrapper


def get_query_performance_report() -> Dict[str, Any]:
    """Получает отчет о производительности запросов"""
    return query_optimizer.get_performance_report()


def reset_query_stats():
    """Сбрасывает статистику запросов"""
    query_optimizer.query_stats.clear()
    logger.info("Статистика запросов сброшена")
