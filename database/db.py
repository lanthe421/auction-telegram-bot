import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from config.settings import (
    DB_MAX_OVERFLOW,
    DB_POOL_SIZE,
    DB_POOL_TIMEOUT,
    get_database_url,
)

logger = logging.getLogger(__name__)

# Создаем движок с оптимизированными настройками
engine = create_engine(
    get_database_url(),
    poolclass=QueuePool,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_timeout=DB_POOL_TIMEOUT,
    pool_pre_ping=True,  # Проверка соединений перед использованием
    pool_recycle=3600,  # Пересоздание соединений каждый час
    echo=False,  # Отключаем SQL логирование в продакшене
)

# Создаем фабрику сессий
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Устанавливает PRAGMA для SQLite для лучшей производительности"""
    if "sqlite" in str(dbapi_connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
        cursor.execute("PRAGMA synchronous=NORMAL")  # Оптимизация скорости
        cursor.execute("PRAGMA cache_size=10000")  # Увеличиваем кэш
        cursor.execute("PRAGMA temp_store=MEMORY")  # Временные таблицы в памяти
        cursor.execute("PRAGMA mmap_size=268435456")  # 256MB для mmap
        cursor.close()


@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_connection, connection_record, connection_proxy):
    """Логируем создание новых соединений"""
    logger.debug(f"Создано новое соединение с БД. Всего активных: {engine.pool.size()}")


@event.listens_for(engine, "checkin")
def receive_checkin(dbapi_connection, connection_record):
    """Логируем возврат соединений в пул"""
    logger.debug(f"Соединение возвращено в пул. Всего активных: {engine.pool.size()}")


def init_db():
    """Инициализация базы данных"""
    try:
        from database.models import Base, User, UserRole

        Base.metadata.create_all(bind=engine)
        logger.info("База данных инициализирована успешно")

        # Сидинг базовых ролей: создаем по одному суперадмину и модератору, если их нет
        db = SessionLocal()
        try:
            # Проверяем наличие хотя бы одного SUPER_ADMIN
            super_admin_exists = (
                db.query(User).filter(User.role == UserRole.SUPER_ADMIN).first()
            )
            if not super_admin_exists:
                seed_sa = User(
                    telegram_id=999000001,
                    username="superadmin",
                    first_name="SuperAdmin",
                    role=UserRole.SUPER_ADMIN,
                )
                db.add(seed_sa)

            # Проверяем наличие хотя бы одного MODERATOR
            moderator_exists = (
                db.query(User).filter(User.role == UserRole.MODERATOR).first()
            )
            if not moderator_exists:
                seed_mod = User(
                    telegram_id=999000002,
                    username="moderator",
                    first_name="Moderator",
                    role=UserRole.MODERATOR,
                )
                db.add(seed_mod)

            db.commit()
        except Exception as e:
            logger.error(f"Ошибка при создании базовых пользователей ролей: {e}")
            db.rollback()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Ошибка при инициализации БД: {e}")
        raise


def get_db() -> Generator[Session, None, None]:
    """Генератор для получения сессии БД"""
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Ошибка в сессии БД: {e}")
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Контекстный менеджер для сессии БД"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        logger.error(f"Ошибка в сессии БД: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def close_db():
    """Закрывает все соединения с БД"""
    try:
        engine.dispose()
        logger.info("Соединения с БД закрыты")
    except Exception as e:
        logger.error(f"Ошибка при закрытии соединений с БД: {e}")


def health_check() -> bool:
    """Проверка здоровья БД"""
    try:
        from sqlalchemy import text

        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Ошибка проверки здоровья БД: {e}")
        return False


def get_db_stats() -> dict:
    """Получение статистики БД"""
    try:
        stats = {
            "pool_size": engine.pool.size(),
            "checked_in": engine.pool.checkedin(),
            "checked_out": engine.pool.checkedout(),
            "overflow": engine.pool.overflow(),
            "invalid": engine.pool.invalid(),
        }
        return stats
    except Exception as e:
        logger.error(f"Ошибка получения статистики БД: {e}")
        return {}
