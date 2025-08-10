"""
Менеджер кэширования для оптимизации производительности
"""

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class CacheItem:
    """Элемент кэша"""

    value: Any
    timestamp: float
    ttl: int  # время жизни в секундах
    access_count: int = 0
    last_access: float = 0


class LRUCache:
    """LRU кэш с TTL"""

    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.cache: OrderedDict = OrderedDict()
        self.lock = threading.RLock()
        self.cleanup_thread = None
        self.is_running = False

    def start_cleanup(self, interval: int = 60):
        """Запускает фоновую очистку устаревших элементов"""
        if self.is_running:
            return

        self.is_running = True
        self.cleanup_thread = threading.Thread(
            target=self._cleanup_loop, args=(interval,), daemon=True
        )
        self.cleanup_thread.start()
        logger.info(f"Запущена фоновая очистка кэша с интервалом {interval}с")

    def stop_cleanup(self):
        """Останавливает фоновую очистку"""
        self.is_running = False
        if self.cleanup_thread:
            self.cleanup_thread.join(timeout=5)

    def _cleanup_loop(self, interval: int):
        """Цикл очистки устаревших элементов"""
        while self.is_running:
            try:
                self._cleanup_expired()
                time.sleep(interval)
            except Exception as e:
                logger.error(f"Ошибка в цикле очистки кэша: {e}")

    def _cleanup_expired(self):
        """Удаляет устаревшие элементы"""
        current_time = time.time()
        expired_keys = []

        with self.lock:
            for key, item in self.cache.items():
                if current_time - item.timestamp > item.ttl:
                    expired_keys.append(key)

            for key in expired_keys:
                del self.cache[key]

        if expired_keys:
            logger.debug(f"Удалено {len(expired_keys)} устаревших элементов кэша")

    def get(self, key: str) -> Optional[Any]:
        """Получает значение из кэша"""
        with self.lock:
            if key in self.cache:
                item = self.cache[key]
                current_time = time.time()

                # Проверяем TTL
                if current_time - item.timestamp > item.ttl:
                    del self.cache[key]
                    return None

                # Обновляем статистику доступа
                item.access_count += 1
                item.last_access = current_time

                # Перемещаем в конец (LRU)
                self.cache.move_to_end(key)

                return item.value

        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Устанавливает значение в кэш"""
        if ttl is None:
            ttl = self.default_ttl

        with self.lock:
            # Проверяем размер кэша
            if len(self.cache) >= self.max_size:
                # Удаляем самый старый элемент
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]

            # Создаем новый элемент
            item = CacheItem(value=value, timestamp=time.time(), ttl=ttl)

            self.cache[key] = item

            # Перемещаем в конец
            self.cache.move_to_end(key)

        return True

    def delete(self, key: str) -> bool:
        """Удаляет элемент из кэша"""
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                return True
        return False

    def clear(self):
        """Очищает весь кэш"""
        with self.lock:
            self.cache.clear()

    def size(self) -> int:
        """Возвращает размер кэша"""
        with self.lock:
            return len(self.cache)

    def keys(self) -> list:
        """Возвращает список ключей"""
        with self.lock:
            return list(self.cache.keys())

    def get_stats(self) -> Dict:
        """Возвращает статистику кэша"""
        with self.lock:
            if not self.cache:
                return {"size": 0, "avg_ttl": 0, "avg_access_count": 0}

            total_ttl = sum(item.ttl for item in self.cache.values())
            total_access = sum(item.access_count for item in self.cache.values())

            return {
                "size": len(self.cache),
                "avg_ttl": total_ttl / len(self.cache),
                "avg_access_count": total_access / len(self.cache),
                "max_size": self.max_size,
                "utilization": len(self.cache) / self.max_size * 100,
            }


class CacheManager:
    """Менеджер кэширования с несколькими уровнями"""

    def __init__(self):
        self.caches: Dict[str, LRUCache] = {}
        self.default_cache = LRUCache()

    def get_cache(self, name: str = "default") -> LRUCache:
        """Получает кэш по имени"""
        if name not in self.caches:
            self.caches[name] = LRUCache()
        return self.caches[name]

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        cache_name: str = "default",
    ):
        """Устанавливает значение в указанный кэш"""
        cache = self.get_cache(cache_name)
        return cache.set(key, value, ttl)

    def get(self, key: str, cache_name: str = "default") -> Optional[Any]:
        """Получает значение из указанного кэша"""
        cache = self.get_cache(cache_name)
        return cache.get(key)

    def delete(self, key: str, cache_name: str = "default") -> bool:
        """Удаляет значение из указанного кэша"""
        cache = self.get_cache(cache_name)
        return cache.delete(key)

    def clear_cache(self, cache_name: str = "default"):
        """Очищает указанный кэш"""
        cache = self.get_cache(cache_name)
        cache.clear()

    def clear_all(self):
        """Очищает все кэши"""
        for cache in self.caches.values():
            cache.clear()
        self.default_cache.clear()

    def get_all_stats(self) -> Dict:
        """Возвращает статистику всех кэшей"""
        stats = {"default": self.default_cache.get_stats(), "caches": {}}

        for name, cache in self.caches.items():
            stats["caches"][name] = cache.get_stats()

        return stats

    def start_cleanup(self, interval: int = 60):
        """Запускает очистку для всех кэшей"""
        self.default_cache.start_cleanup(interval)
        for cache in self.caches.values():
            cache.start_cleanup(interval)

    def stop_cleanup(self):
        """Останавливает очистку для всех кэшей"""
        self.default_cache.stop_cleanup()
        for cache in self.caches.values():
            cache.stop_cleanup()


# Глобальный менеджер кэша
cache_manager = CacheManager()


def cache_result(ttl: int = 300, cache_name: str = "default"):
    """Декоратор для кэширования результатов функций"""

    def decorator(func: Callable):
        def wrapper(*args, **kwargs):
            # Создаем ключ кэша на основе функции и аргументов
            cache_key = (
                f"{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"
            )

            # Пытаемся получить из кэша
            cached_result = cache_manager.get(cache_key, cache_name)
            if cached_result is not None:
                return cached_result

            # Выполняем функцию и кэшируем результат
            result = func(*args, **kwargs)
            cache_manager.set(cache_key, result, ttl, cache_name)

            return result

        return wrapper

    return decorator


def invalidate_cache_pattern(pattern: str, cache_name: str = "default"):
    """Инвалидирует кэш по паттерну ключа"""
    cache = cache_manager.get_cache(cache_name)
    keys_to_delete = [key for key in cache.keys() if pattern in key]

    for key in keys_to_delete:
        cache.delete(key)

    logger.info(
        f"Инвалидировано {len(keys_to_delete)} элементов кэша по паттерну '{pattern}'"
    )


def get_cache_stats(cache_name: str = "default") -> Dict:
    """Возвращает статистику кэша"""
    return cache_manager.get_cache(cache_name).get_stats()


def start_cache_cleanup(interval: int = 60):
    """Запускает очистку всех кэшей"""
    cache_manager.start_cleanup(interval)


def stop_cache_cleanup():
    """Останавливает очистку всех кэшей"""
    cache_manager.stop_cleanup()
