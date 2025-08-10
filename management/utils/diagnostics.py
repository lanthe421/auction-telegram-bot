"""
Диагностика и мониторинг системы
"""

import logging
import os
import platform
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

from config.settings import get_media_path
from database.db import get_db_stats, health_check
from management.utils.cache_manager import get_all_cache_stats, get_cache_stats
from management.utils.index_manager import get_index_performance_report
from management.utils.performance_monitor import (
    get_performance_alerts,
    get_performance_summary,
)
from management.utils.query_optimizer import get_query_performance_report

logger = logging.getLogger(__name__)


class SystemDiagnostics:
    """Диагностика системы"""

    def __init__(self):
        self.start_time = datetime.now()
        self.checks_performed = []

    def run_full_diagnostics(self) -> Dict[str, Any]:
        """Запускает полную диагностику системы"""
        logger.info("Запуск полной диагностики системы...")

        try:
            results = {
                "timestamp": datetime.now().isoformat(),
                "system_info": self._get_system_info(),
                "performance_metrics": self._get_performance_metrics(),
                "database_health": self._get_database_health(),
                "cache_status": self._get_cache_status(),
                "query_performance": self._get_query_performance(),
                "index_optimization": self._get_index_optimization(),
                "media_status": self._get_media_status(),
                "disk_usage": self._get_disk_usage(),
                "memory_analysis": self._get_memory_analysis(),
                "network_status": self._get_network_status(),
                "recommendations": self._get_recommendations(),
                "overall_health_score": 0,
            }

            # Вычисляем общий показатель здоровья системы
            results["overall_health_score"] = self._calculate_health_score(results)

            # Записываем результаты проверки
            self.checks_performed.append(
                {
                    "timestamp": datetime.now(),
                    "health_score": results["overall_health_score"],
                    "issues_found": len(self._get_all_issues(results)),
                }
            )

            logger.info(
                f"Диагностика завершена. Общий показатель здоровья: {results['overall_health_score']}/100"
            )
            return results

        except Exception as e:
            logger.error(f"Ошибка при выполнении диагностики: {e}")
            return {"error": str(e)}

    def _get_system_info(self) -> Dict[str, Any]:
        """Получает информацию о системе"""
        try:
            return {
                "platform": platform.platform(),
                "python_version": sys.version,
                "architecture": platform.architecture(),
                "processor": platform.processor(),
                "hostname": platform.node(),
                "uptime": self._get_system_uptime(),
                "python_path": sys.executable,
                "working_directory": os.getcwd(),
            }
        except Exception as e:
            logger.error(f"Ошибка при получении информации о системе: {e}")
            return {"error": str(e)}

    def _get_performance_metrics(self) -> Dict[str, Any]:
        """Получает метрики производительности"""
        try:
            # Получаем сводку за последние 24 часа
            summary = get_performance_summary(hours=24)
            alerts = get_performance_alerts()

            return {
                "summary": summary,
                "alerts": alerts,
                "current_cpu": psutil.cpu_percent(interval=1),
                "current_memory": psutil.virtual_memory().percent,
                "current_disk": psutil.disk_usage("/").percent,
            }
        except Exception as e:
            logger.error(f"Ошибка при получении метрик производительности: {e}")
            return {"error": str(e)}

    def _get_database_health(self) -> Dict[str, Any]:
        """Проверяет здоровье базы данных"""
        try:
            health_status = health_check()
            db_stats = get_db_stats()

            return {
                "is_healthy": health_status,
                "connection_stats": db_stats,
                "database_file": self._get_database_file_info(),
                "last_check": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Ошибка при проверке здоровья БД: {e}")
            return {"error": str(e)}

    def _get_cache_status(self) -> Dict[str, Any]:
        """Получает статус кэша"""
        try:
            cache_stats = get_all_cache_stats()

            return {
                "stats": cache_stats,
                "total_caches": len(cache_stats.get("caches", {})),
                "default_cache_utilization": cache_stats.get("default", {}).get(
                    "utilization", 0
                ),
                "overall_efficiency": self._calculate_cache_efficiency(cache_stats),
            }
        except Exception as e:
            logger.error(f"Ошибка при получении статуса кэша: {e}")
            return {"error": str(e)}

    def _get_query_performance(self) -> Dict[str, Any]:
        """Получает производительность запросов"""
        try:
            return get_query_performance_report()
        except Exception as e:
            logger.error(f"Ошибка при получении производительности запросов: {e}")
            return {"error": str(e)}

    def _get_index_optimization(self) -> Dict[str, Any]:
        """Получает информацию об оптимизации индексов"""
        try:
            return get_index_performance_report()
        except Exception as e:
            logger.error(f"Ошибка при получении информации об индексах: {e}")
            return {"error": str(e)}

    def _get_media_status(self) -> Dict[str, Any]:
        """Проверяет статус медиа файлов"""
        try:
            media_path = get_media_path()

            if not media_path.exists():
                return {"status": "not_found", "path": str(media_path)}

            # Подсчитываем файлы
            total_files = 0
            total_size = 0
            file_types = {}

            for file_path in media_path.rglob("*"):
                if file_path.is_file():
                    total_files += 1
                    total_size += file_path.stat().st_size

                    ext = file_path.suffix.lower()
                    file_types[ext] = file_types.get(ext, 0) + 1

            return {
                "status": "ok",
                "path": str(media_path),
                "total_files": total_files,
                "total_size_mb": total_size / (1024 * 1024),
                "file_types": file_types,
                "exists": True,
            }
        except Exception as e:
            logger.error(f"Ошибка при проверке статуса медиа: {e}")
            return {"error": str(e)}

    def _get_disk_usage(self) -> Dict[str, Any]:
        """Анализирует использование диска"""
        try:
            disk_usage = psutil.disk_usage("/")
            disk_io = psutil.disk_io_counters()

            return {
                "total_gb": disk_usage.total / (1024**3),
                "used_gb": disk_usage.used / (1024**3),
                "free_gb": disk_usage.free / (1024**3),
                "usage_percent": disk_usage.percent,
                "read_bytes": disk_io.read_bytes if disk_io else 0,
                "write_bytes": disk_io.write_bytes if disk_io else 0,
                "is_critical": disk_usage.percent > 90,
            }
        except Exception as e:
            logger.error(f"Ошибка при анализе использования диска: {e}")
            return {"error": str(e)}

    def _get_memory_analysis(self) -> Dict[str, Any]:
        """Анализирует использование памяти"""
        try:
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()

            return {
                "total_gb": memory.total / (1024**3),
                "available_gb": memory.available / (1024**3),
                "used_gb": memory.used / (1024**3),
                "usage_percent": memory.percent,
                "swap_total_gb": swap.total / (1024**3),
                "swap_used_gb": swap.used / (1024**3),
                "swap_usage_percent": (
                    (swap.used / swap.total * 100) if swap.total > 0 else 0
                ),
                "is_critical": memory.percent > 90,
            }
        except Exception as e:
            logger.error(f"Ошибка при анализе памяти: {e}")
            return {"error": str(e)}

    def _get_network_status(self) -> Dict[str, Any]:
        """Проверяет статус сети"""
        try:
            network_io = psutil.net_io_counters()
            network_connections = len(psutil.net_connections())

            return {
                "bytes_sent_mb": network_io.bytes_sent / (1024 * 1024),
                "bytes_recv_mb": network_io.bytes_recv / (1024 * 1024),
                "active_connections": network_connections,
                "packets_sent": network_io.packets_sent,
                "packets_recv": network_io.packets_recv,
            }
        except Exception as e:
            logger.error(f"Ошибка при проверке сети: {e}")
            return {"error": str(e)}

    def _get_recommendations(self) -> List[Dict[str, Any]]:
        """Получает рекомендации по оптимизации"""
        recommendations = []

        try:
            # Проверяем производительность
            perf_summary = get_performance_summary(hours=1)
            if perf_summary.get("avg_cpu_percent", 0) > 80:
                recommendations.append(
                    {
                        "type": "performance",
                        "priority": "high",
                        "message": "Высокая загрузка CPU. Рассмотрите оптимизацию алгоритмов или увеличение ресурсов.",
                        "action": "Оптимизировать код или увеличить ресурсы сервера",
                    }
                )

            # Проверяем память
            memory = psutil.virtual_memory()
            if memory.percent > 85:
                recommendations.append(
                    {
                        "type": "memory",
                        "priority": "high",
                        "message": "Высокое потребление памяти. Проверьте утечки памяти.",
                        "action": "Анализ использования памяти и оптимизация",
                    }
                )

            # Проверяем диск
            disk = psutil.disk_usage("/")
            if disk.percent > 85:
                recommendations.append(
                    {
                        "type": "disk",
                        "priority": "medium",
                        "message": "Мало свободного места на диске.",
                        "action": "Очистка временных файлов и логов",
                    }
                )

            # Проверяем кэш
            cache_stats = get_all_cache_stats()
            default_cache = cache_stats.get("default", {})
            if default_cache.get("utilization", 0) > 90:
                recommendations.append(
                    {
                        "type": "cache",
                        "priority": "medium",
                        "message": "Кэш почти заполнен. Рассмотрите увеличение размера.",
                        "action": "Увеличить размер кэша или оптимизировать TTL",
                    }
                )

            # Проверяем индексы
            index_report = get_index_performance_report()
            if index_report.get("overall_coverage", 0) < 70:
                recommendations.append(
                    {
                        "type": "database",
                        "priority": "medium",
                        "message": "Низкое покрытие индексами. Создайте рекомендуемые индексы.",
                        "action": "Создать рекомендуемые индексы для оптимизации запросов",
                    }
                )

        except Exception as e:
            logger.error(f"Ошибка при получении рекомендаций: {e}")

        return recommendations

    def _calculate_health_score(self, results: Dict[str, Any]) -> int:
        """Вычисляет общий показатель здоровья системы"""
        score = 100

        try:
            # Штрафы за проблемы
            if results.get("performance_metrics", {}).get("alerts"):
                score -= len(results["performance_metrics"]["alerts"]) * 5

            if not results.get("database_health", {}).get("is_healthy", True):
                score -= 20

            if results.get("disk_usage", {}).get("is_critical", False):
                score -= 15

            if results.get("memory_analysis", {}).get("is_critical", False):
                score -= 15

            # Бонусы за хорошие показатели
            cache_efficiency = results.get("cache_status", {}).get(
                "overall_efficiency", 0
            )
            if cache_efficiency > 80:
                score += 5

            index_coverage = results.get("index_optimization", {}).get(
                "overall_coverage", 0
            )
            if index_coverage > 80:
                score += 5

            # Ограничиваем диапазон
            score = max(0, min(100, score))

        except Exception as e:
            logger.error(f"Ошибка при вычислении показателя здоровья: {e}")
            score = 50

        return score

    def _calculate_cache_efficiency(self, cache_stats: Dict[str, Any]) -> float:
        """Вычисляет эффективность кэша"""
        try:
            total_utilization = 0
            cache_count = 0

            for cache_name, stats in cache_stats.get("caches", {}).items():
                if isinstance(stats, dict) and "utilization" in stats:
                    total_utilization += stats["utilization"]
                    cache_count += 1

            # Добавляем default кэш
            default_stats = cache_stats.get("default", {})
            if "utilization" in default_stats:
                total_utilization += default_stats["utilization"]
                cache_count += 1

            return total_utilization / max(cache_count, 1)

        except Exception:
            return 0

    def _get_all_issues(self, results: Dict[str, Any]) -> List[str]:
        """Получает все найденные проблемы"""
        issues = []

        try:
            # Проблемы с производительностью
            alerts = results.get("performance_metrics", {}).get("alerts", [])
            issues.extend(alerts)

            # Проблемы с БД
            if not results.get("database_health", {}).get("is_healthy", True):
                issues.append("Проблемы с базой данных")

            # Проблемы с диском
            if results.get("disk_usage", {}).get("is_critical", False):
                issues.append("Критическое использование диска")

            # Проблемы с памятью
            if results.get("memory_analysis", {}).get("is_critical", False):
                issues.append("Критическое использование памяти")

        except Exception as e:
            logger.error(f"Ошибка при получении проблем: {e}")

        return issues

    def _get_system_uptime(self) -> str:
        """Получает время работы системы"""
        try:
            uptime_seconds = time.time() - psutil.boot_time()
            uptime = timedelta(seconds=uptime_seconds)
            return str(uptime)
        except:
            return "Неизвестно"

    def _get_database_file_info(self) -> Dict[str, Any]:
        """Получает информацию о файле базы данных"""
        try:
            db_path = Path("db.db")
            if db_path.exists():
                stat = db_path.stat()
                return {
                    "path": str(db_path.absolute()),
                    "size_mb": stat.st_size / (1024 * 1024),
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "exists": True,
                }
            else:
                return {"exists": False}
        except Exception as e:
            return {"error": str(e)}

    def get_health_summary(self) -> Dict[str, Any]:
        """Получает краткую сводку здоровья системы"""
        try:
            return {
                "overall_score": self._calculate_health_score({}),
                "issues_count": len(self._get_all_issues({})),
                "last_check": self.start_time.isoformat(),
                "checks_performed": len(self.checks_performed),
            }
        except Exception as e:
            logger.error(f"Ошибка при получении сводки здоровья: {e}")
            return {"error": str(e)}

    def export_diagnostics_report(self, filepath: str) -> bool:
        """Экспортирует отчет диагностики в файл"""
        try:
            import json

            report = self.run_full_diagnostics()

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False, default=str)

            logger.info(f"Отчет диагностики экспортирован в {filepath}")
            return True

        except Exception as e:
            logger.error(f"Ошибка при экспорте отчета: {e}")
            return False


# Глобальный экземпляр диагностики
system_diagnostics = SystemDiagnostics()


def run_system_diagnostics() -> Dict[str, Any]:
    """Запускает диагностику системы"""
    return system_diagnostics.run_full_diagnostics()


def get_system_health_summary() -> Dict[str, Any]:
    """Получает сводку здоровья системы"""
    return system_diagnostics.get_health_summary()


def export_diagnostics_report(filepath: str) -> bool:
    """Экспортирует отчет диагностики"""
    return system_diagnostics.export_diagnostics_report(filepath)


def quick_health_check() -> Dict[str, Any]:
    """Быстрая проверка здоровья системы"""
    try:
        return {
            "timestamp": datetime.now().isoformat(),
            "database_healthy": health_check(),
            "cpu_usage": psutil.cpu_percent(interval=1),
            "memory_usage": psutil.virtual_memory().percent,
            "disk_usage": psutil.disk_usage("/").percent,
            "uptime": system_diagnostics._get_system_uptime(),
        }
    except Exception as e:
        logger.error(f"Ошибка при быстрой проверке здоровья: {e}")
        return {"error": str(e)}
