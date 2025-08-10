"""
Мониторинг производительности системы
Упрощенная версия без внешних зависимостей
"""

import logging
import os
import platform
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """Монитор производительности системы"""

    def __init__(self):
        self.metrics_history = defaultdict(lambda: deque(maxlen=1000))
        self.start_time = time.time()
        self.monitoring = False
        self.monitor_thread = None

        # Базовые метрики системы
        self.system_info = self._get_system_info()

    def _get_system_info(self) -> Dict[str, Any]:
        """Получает базовую информацию о системе"""
        try:
            return {
                "platform": platform.platform(),
                "python_version": platform.python_version(),
                "processor": platform.processor(),
                "machine": platform.machine(),
                "node": platform.node(),
                "start_time": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Ошибка при получении информации о системе: {e}")
            return {"error": str(e)}

    def _get_memory_info(self) -> Dict[str, Any]:
        """Получает информацию о памяти (упрощенная версия)"""
        try:
            # Используем встроенные модули Python
            import gc

            gc.collect()  # Принудительная очистка памяти

            # Простая оценка использования памяти
            memory_usage = 0
            try:
                # Попытка получить информацию о памяти через os
                if hasattr(os, "getpid"):
                    import psutil

                    process = psutil.Process(os.getpid())
                    memory_usage = process.memory_info().rss / (1024 * 1024)  # MB
                else:
                    memory_usage = 50.0  # Значение по умолчанию
            except ImportError:
                # Если psutil недоступен, используем приблизительную оценку
                memory_usage = 50.0

            return {
                "memory_usage_mb": memory_usage,
                "memory_usage_percent": min(memory_usage / 100, 100),  # Приблизительно
                "gc_objects": len(gc.get_objects()),
                "gc_collections": gc.get_count(),
            }
        except Exception as e:
            logger.error(f"Ошибка при получении информации о памяти: {e}")
            return {"memory_usage_mb": 0, "memory_usage_percent": 0}

    def _get_disk_info(self) -> Dict[str, Any]:
        """Получает информацию о диске"""
        try:
            current_dir = Path.cwd()
            disk_usage = 0

            try:
                # Попытка получить статистику диска
                if hasattr(os, "statvfs"):
                    stat = os.statvfs(current_dir)
                    total = stat.f_blocks * stat.f_frsize
                    free = stat.f_bavail * stat.f_frsize
                    used = total - free
                    disk_usage = (used / total) * 100
                else:
                    disk_usage = 60.0  # Значение по умолчанию
            except Exception:
                disk_usage = 60.0

            return {
                "disk_usage_percent": disk_usage,
                "current_directory": str(current_dir),
                "disk_io": 0.0,  # Упрощенная версия
            }
        except Exception as e:
            logger.error(f"Ошибка при получении информации о диске: {e}")
            return {"disk_usage_percent": 0, "disk_io": 0.0}

    def _get_cpu_info(self) -> Dict[str, Any]:
        """Получает информацию о CPU (упрощенная версия)"""
        try:
            # Простая оценка нагрузки CPU
            cpu_usage = 0

            try:
                # Попытка получить реальную нагрузку CPU
                if hasattr(os, "getloadavg"):
                    load_avg = os.getloadavg()
                    cpu_usage = min(load_avg[0] * 20, 100)  # Приблизительная оценка
                else:
                    cpu_usage = 25.0  # Значение по умолчанию
            except Exception:
                cpu_usage = 25.0

            return {
                "cpu_usage_percent": cpu_usage,
                "load_average": (
                    [0.0, 0.0, 0.0]
                    if not hasattr(os, "getloadavg")
                    else list(os.getloadavg())
                ),
            }
        except Exception as e:
            logger.error(f"Ошибка при получении информации о CPU: {e}")
            return {"cpu_usage_percent": 0, "load_average": [0.0, 0.0, 0.0]}

    def _get_network_info(self) -> Dict[str, Any]:
        """Получает информацию о сети (упрощенная версия)"""
        try:
            return {
                "network_io_mbps": 0.0,  # Упрощенная версия
                "connections": 0,
                "bandwidth_usage": 0.0,
            }
        except Exception as e:
            logger.error(f"Ошибка при получении информации о сети: {e}")
            return {"network_io_mbps": 0.0, "connections": 0, "bandwidth_usage": 0.0}

    def collect_metrics(self) -> Dict[str, Any]:
        """Собирает все метрики производительности"""
        try:
            timestamp = time.time()

            metrics = {
                "timestamp": timestamp,
                "uptime": timestamp - self.start_time,
                "memory": self._get_memory_info(),
                "cpu": self._get_cpu_info(),
                "disk": self._get_disk_info(),
                "network": self._get_network_info(),
                "system": self.system_info,
            }

            # Сохраняем в историю
            for key, value in metrics.items():
                if key != "timestamp":
                    self.metrics_history[key].append((timestamp, value))

            return metrics

        except Exception as e:
            logger.error(f"Ошибка при сборе метрик: {e}")
            return {"error": str(e), "timestamp": time.time()}

    def get_performance_summary(self, hours: int = 1) -> Dict[str, Any]:
        """Получает сводку производительности за указанное время"""
        try:
            current_time = time.time()
            cutoff_time = current_time - (hours * 3600)

            # Собираем текущие метрики
            current_metrics = self.collect_metrics()

            # Анализируем историю
            summary = {
                "cpu_usage": current_metrics["cpu"]["cpu_usage_percent"],
                "memory_usage": current_metrics["memory"]["memory_usage_percent"],
                "disk_usage": current_metrics["disk"]["disk_usage_percent"],
                "network_io": current_metrics["network"]["network_io_mbps"],
                "uptime_hours": (current_time - self.start_time) / 3600,
                "system_health": self._calculate_health_score(current_metrics),
            }

            # Добавляем статистику по времени
            if self.metrics_history["cpu"]:
                cpu_values = [
                    v[1]["cpu_usage_percent"]
                    for v in self.metrics_history["cpu"]
                    if v[0] >= cutoff_time
                ]
                if cpu_values:
                    summary["avg_cpu"] = sum(cpu_values) / len(cpu_values)
                    summary["max_cpu"] = max(cpu_values)
                    summary["min_cpu"] = min(cpu_values)

            if self.metrics_history["memory"]:
                memory_values = [
                    v[1]["memory_usage_percent"]
                    for v in self.metrics_history["memory"]
                    if v[0] >= cutoff_time
                ]
                if memory_values:
                    summary["avg_memory"] = sum(memory_values) / len(memory_values)
                    summary["max_memory"] = max(memory_values)
                    summary["min_memory"] = min(memory_values)

            return summary

        except Exception as e:
            logger.error(f"Ошибка при получении сводки производительности: {e}")
            return {"error": str(e)}

    def _calculate_health_score(self, metrics: Dict[str, Any]) -> int:
        """Вычисляет общий показатель здоровья системы (0-100)"""
        try:
            score = 100

            # CPU
            cpu_usage = metrics["cpu"]["cpu_usage_percent"]
            if cpu_usage > 90:
                score -= 30
            elif cpu_usage > 80:
                score -= 20
            elif cpu_usage > 70:
                score -= 10

            # Память
            memory_usage = metrics["memory"]["memory_usage_percent"]
            if memory_usage > 90:
                score -= 30
            elif memory_usage > 80:
                score -= 20
            elif memory_usage > 70:
                score -= 10

            # Диск
            disk_usage = metrics["disk"]["disk_usage_percent"]
            if disk_usage > 95:
                score -= 25
            elif disk_usage > 90:
                score -= 15
            elif disk_usage > 80:
                score -= 10

            return max(0, score)

        except Exception as e:
            logger.error(f"Ошибка при вычислении показателя здоровья: {e}")
            return 50

    def start_monitoring(self, interval: int = 30):
        """Запускает мониторинг в фоновом режиме"""
        if self.monitoring:
            return

        self.monitoring = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop, args=(interval,), daemon=True
        )
        self.monitor_thread.start()
        logger.info(f"Запущен мониторинг производительности с интервалом {interval}с")

    def stop_monitoring(self):
        """Останавливает мониторинг"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("Мониторинг производительности остановлен")

    def _monitor_loop(self, interval: int):
        """Цикл мониторинга"""
        while self.monitoring:
            try:
                self.collect_metrics()
                time.sleep(interval)
            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга: {e}")
                time.sleep(interval)

    def get_alerts(self) -> List[str]:
        """Получает предупреждения о производительности"""
        alerts = []
        try:
            current_metrics = self.collect_metrics()

            # CPU предупреждения
            cpu_usage = current_metrics["cpu"]["cpu_usage_percent"]
            if cpu_usage > 90:
                alerts.append(f"Критическая нагрузка CPU: {cpu_usage:.1f}%")
            elif cpu_usage > 80:
                alerts.append(f"Высокая нагрузка CPU: {cpu_usage:.1f}%")

            # Память предупреждения
            memory_usage = current_metrics["memory"]["memory_usage_percent"]
            if memory_usage > 90:
                alerts.append(f"Критическое использование памяти: {memory_usage:.1f}%")
            elif memory_usage > 80:
                alerts.append(f"Высокое использование памяти: {memory_usage:.1f}%")

            # Диск предупреждения
            disk_usage = current_metrics["disk"]["disk_usage_percent"]
            if disk_usage > 95:
                alerts.append(f"Критическое использование диска: {disk_usage:.1f}%")
            elif disk_usage > 90:
                alerts.append(f"Высокое использование диска: {disk_usage:.1f}%")

        except Exception as e:
            logger.error(f"Ошибка при получении предупреждений: {e}")
            alerts.append(f"Ошибка мониторинга: {e}")

        return alerts

    def get_system_health(self) -> Dict[str, Any]:
        """Получает общую оценку здоровья системы"""
        try:
            current_metrics = self.collect_metrics()
            health_score = self._calculate_health_score(current_metrics)

            # Определяем статус
            if health_score >= 80:
                status = "Отлично"
            elif health_score >= 60:
                status = "Хорошо"
            elif health_score >= 40:
                status = "Удовлетворительно"
            else:
                status = "Критично"

            # Формируем рекомендации
            recommendations = []

            if current_metrics["cpu"]["cpu_usage_percent"] > 80:
                recommendations.append(
                    "Рассмотрите возможность оптимизации CPU-интенсивных операций"
                )

            if current_metrics["memory"]["memory_usage_percent"] > 80:
                recommendations.append(
                    "Проверьте утечки памяти и оптимизируйте использование"
                )

            if current_metrics["disk"]["disk_usage_percent"] > 90:
                recommendations.append("Освободите место на диске или увеличьте объем")

            return {
                "overall_health_score": health_score,
                "status": status,
                "recommendations": recommendations,
                "last_check": datetime.now().isoformat(),
                "metrics": current_metrics,
            }

        except Exception as e:
            logger.error(f"Ошибка при получении здоровья системы: {e}")
            return {
                "overall_health_score": 0,
                "status": "Ошибка",
                "recommendations": [f"Ошибка мониторинга: {e}"],
                "last_check": datetime.now().isoformat(),
            }


# Глобальный экземпляр монитора
performance_monitor = PerformanceMonitor()


def get_performance_summary(hours: int = 1) -> Dict[str, Any]:
    """Получает сводку производительности"""
    return performance_monitor.get_performance_summary(hours)


def get_system_health() -> Dict[str, Any]:
    """Получает здоровье системы"""
    return performance_monitor.get_system_health()


def get_performance_alerts() -> List[str]:
    """Получает предупреждения о производительности"""
    return performance_monitor.get_alerts()


def start_performance_monitoring(interval: int = 30):
    """Запускает мониторинг производительности"""
    performance_monitor.start_monitoring(interval)


def stop_performance_monitoring():
    """Останавливает мониторинг производительности"""
    performance_monitor.stop_monitoring()


def run_system_diagnostics() -> Dict[str, Any]:
    """Запускает полную диагностику системы"""
    try:
        # Собираем все метрики
        metrics = performance_monitor.collect_metrics()
        health = performance_monitor.get_system_health()
        alerts = performance_monitor.get_alerts()

        # Анализируем проблемы
        issues = []
        if health["overall_health_score"] < 60:
            issues.append("Низкий общий показатель здоровья системы")

        if len(alerts) > 0:
            issues.append(f"Найдено {len(alerts)} предупреждений")

        # Формируем отчет
        return {
            "status": "completed",
            "overall_health_score": health["overall_health_score"],
            "issues": issues,
            "recommendations": health["recommendations"],
            "alerts": alerts,
            "metrics": metrics,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Ошибка при диагностике системы: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
