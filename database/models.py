import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class UserRole(enum.Enum):
    SELLER = "seller"  # Продавец-администратор
    MODERATOR = "moderator"  # Модератор
    SUPPORT = "support"  # Поддержка
    SUPER_ADMIN = "super_admin"  # Супер-администратор


class LotStatus(enum.Enum):
    DRAFT = "draft"  # Черновик
    PENDING = "pending"  # На модерации
    ACTIVE = "active"  # Активный
    SOLD = "sold"  # Продан
    CANCELLED = "cancelled"  # Отменен
    EXPIRED = "expired"  # Истек


class DocumentType(enum.Enum):
    JEWELRY = "jewelry"  # Ювелирные изделия
    HISTORICAL = "historical"  # Исторические ценности
    STANDARD = "standard"  # Стандартные лоты


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)
    username = Column(String(50), nullable=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    role = Column(Enum(UserRole), default=UserRole.SELLER)
    balance = Column(Float, default=0.0)
    is_banned = Column(Boolean, default=False)
    strikes = Column(Integer, default=0)
    successful_payments = Column(Integer, default=0)
    auto_bid_enabled = Column(Boolean, default=False)
    max_bid_amount = Column(Float, nullable=True)  # Максимальная сумма для автоставок
    notifications_enabled = Column(Boolean, default=True)  # Включены ли уведомления
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Отношения
    lots = relationship("Lot", back_populates="seller", foreign_keys="Lot.seller_id")
    bids = relationship("Bid", back_populates="bidder", foreign_keys="Bid.bidder_id")
    payments = relationship(
        "Payment", back_populates="user", foreign_keys="Payment.user_id"
    )
    complaints = relationship(
        "Complaint",
        back_populates="complainant",
        foreign_keys="Complaint.complainant_id",
    )
    auto_bids = relationship(
        "AutoBid", back_populates="user", foreign_keys="AutoBid.user_id"
    )


class Lot(Base):
    __tablename__ = "lots"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    starting_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=False)
    min_bid_increment = Column(Float, nullable=False)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(Enum(LotStatus), default=LotStatus.DRAFT)
    document_type = Column(Enum(DocumentType), default=DocumentType.STANDARD)

    # Медиа и файлы
    images = Column(Text, nullable=True)  # JSON список URL изображений
    files = Column(Text, nullable=True)  # JSON список файлов для скачивания
    location = Column(String(200), nullable=True)  # Геолокация

    # Время
    start_time = Column(DateTime, nullable=True)  # None для немедленного запуска
    end_time = Column(DateTime, nullable=True)  # None для немедленного запуска
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Модерация
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)

    # Telegram интеграция
    telegram_message_id = Column(
        Integer, nullable=True
    )  # ID сообщения в Telegram канале
    rejection_reason = Column(Text, nullable=True)

    # Дополнительная информация
    seller_link = Column(String(200), nullable=True)  # Ссылка на продавца

    # Отношения
    seller = relationship("User", back_populates="lots", foreign_keys=[seller_id])
    bids = relationship("Bid", back_populates="lot", foreign_keys="Bid.lot_id")
    documents = relationship(
        "Document", back_populates="lot", foreign_keys="Document.lot_id"
    )
    auto_bids = relationship(
        "AutoBid", back_populates="lot", foreign_keys="AutoBid.lot_id"
    )


class Bid(Base):
    __tablename__ = "bids"

    id = Column(Integer, primary_key=True, index=True)
    lot_id = Column(Integer, ForeignKey("lots.id"), nullable=False)
    bidder_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    is_auto_bid = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Отношения
    lot = relationship("Lot", back_populates="bids", foreign_keys=[lot_id])
    bidder = relationship("User", back_populates="bids", foreign_keys=[bidder_id])


class AutoBid(Base):
    """Модель для хранения автоставок пользователей на конкретные лоты"""

    __tablename__ = "auto_bids"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    lot_id = Column(Integer, ForeignKey("lots.id"), nullable=False)
    target_amount = Column(Float, nullable=False)  # Целевая сумма автоставки
    is_active = Column(Boolean, default=True)  # Активна ли автоставка
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Отношения
    user = relationship("User", back_populates="auto_bids", foreign_keys=[user_id])
    lot = relationship("Lot", back_populates="auto_bids", foreign_keys=[lot_id])


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    lot_id = Column(Integer, ForeignKey("lots.id"), nullable=True)
    amount = Column(Float, nullable=False)
    payment_type = Column(
        String(50), nullable=False
    )  # "commission", "penalty", "deposit"
    status = Column(String(20), default="pending")  # pending, completed, failed
    transaction_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    # Отношения
    user = relationship("User", back_populates="payments", foreign_keys=[user_id])
    lot = relationship("Lot", foreign_keys=[lot_id])


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    lot_id = Column(Integer, ForeignKey("lots.id"), nullable=False)
    document_type = Column(Enum(DocumentType), nullable=False)
    content = Column(Text, nullable=False)  # Содержимое документа
    file_path = Column(String(500), nullable=True)  # Путь к файлу
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Отношения
    lot = relationship("Lot", back_populates="documents", foreign_keys=[lot_id])


class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(Integer, primary_key=True, index=True)
    complainant_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    lot_id = Column(Integer, ForeignKey("lots.id"), nullable=True)
    reason = Column(Text, nullable=False)
    evidence = Column(Text, nullable=True)  # JSON с доказательствами
    status = Column(String(20), default="pending")  # pending, reviewed, resolved
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    resolution = Column(Text, nullable=True)
    is_resolved = Column(Boolean, default=False)  # Добавляем поле is_resolved
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Отношения
    complainant = relationship(
        "User",
        foreign_keys=[complainant_id],
    )
    target_user = relationship("User", foreign_keys=[target_user_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    lot = relationship("Lot", foreign_keys=[lot_id])


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    notification_type = Column(
        String(50), nullable=False
    )  # bid, auction_end, payment, etc.
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Отношения
    user = relationship("User", foreign_keys=[user_id])


class SupportQuestion(Base):
    __tablename__ = "support_questions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    question = Column(Text, nullable=False)
    status = Column(String(20), default="pending")  # pending, answered, closed
    answer = Column(Text, nullable=True)
    answered_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    answered_at = Column(DateTime, nullable=True)
    notified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Отношения
    user = relationship("User", foreign_keys=[user_id])
    moderator = relationship("User", foreign_keys=[answered_by])
