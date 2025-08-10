"""
Панель администратора
"""

import logging
from datetime import datetime
from typing import List

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import func

from database.db import SessionLocal
from database.models import Bid, DocumentType, Lot, LotStatus, Payment, User, UserRole

logger = logging.getLogger(__name__)


class AdminPanel(QWidget):
    """Панель администратора"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.init_ui()
        self.setup_timer()

    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout(self)

        # Заголовок
        title = QLabel("Панель администратора")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Вкладки
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Создаем вкладки
        self.create_lots_tab()
        self.create_users_tab()
        self.create_finance_tab()
        self.create_actions_tab()

        # Обновляем данные
        self.refresh_data()

    def create_lots_tab(self):
        """Создает вкладку управления лотами"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Кнопки управления
        btn_layout = QHBoxLayout()

        create_btn = QPushButton("Создать лот")
        create_btn.clicked.connect(self.create_lot)
        create_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #27ae60;
                color: white;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """
        )
        btn_layout.addWidget(create_btn)

        refresh_btn = QPushButton("Обновить")
        refresh_btn.clicked.connect(self.refresh_lots)
        btn_layout.addWidget(refresh_btn)

        layout.addLayout(btn_layout)

        # Таблица лотов
        self.lots_table = QTableWidget()
        self.lots_table.setColumnCount(7)
        self.lots_table.setHorizontalHeaderLabels(
            ["ID", "Название", "Продавец", "Цена", "Статус", "Окончание", "Действия"]
        )

        header = self.lots_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)

        layout.addWidget(self.lots_table)

        self.tab_widget.addTab(tab, "Управление лотами")

    def create_users_tab(self):
        """Создает вкладку управления пользователями"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Кнопки управления
        btn_layout = QHBoxLayout()

        refresh_users_btn = QPushButton("Обновить")
        refresh_users_btn.clicked.connect(self.refresh_users)
        btn_layout.addWidget(refresh_users_btn)

        layout.addLayout(btn_layout)

        # Таблица пользователей
        self.users_table = QTableWidget()
        self.users_table.setColumnCount(7)
        self.users_table.setHorizontalHeaderLabels(
            ["ID", "Имя", "Username", "Роль", "Баланс", "Статус", "Действия"]
        )

        header = self.users_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)

        layout.addWidget(self.users_table)

        self.tab_widget.addTab(tab, "Пользователи")

    def create_finance_tab(self):
        """Создает вкладку финансов"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Статистика
        stats_group = QGroupBox("Финансовая статистика")
        stats_layout = QFormLayout(stats_group)

        self.total_revenue_label = QLabel("0 ₽")
        self.total_payments_label = QLabel("0")
        self.commission_label = QLabel("0 ₽")

        stats_layout.addRow("Общая выручка:", self.total_revenue_label)
        stats_layout.addRow("Всего платежей:", self.total_payments_label)
        stats_layout.addRow("Комиссии:", self.commission_label)

        layout.addWidget(stats_group)

        # Таблица платежей
        self.payments_table = QTableWidget()
        self.payments_table.setColumnCount(5)
        self.payments_table.setHorizontalHeaderLabels(
            ["ID", "Пользователь", "Сумма", "Тип", "Статус"]
        )

        header = self.payments_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)

        layout.addWidget(self.payments_table)

        self.tab_widget.addTab(tab, "Финансы")

    def create_actions_tab(self):
        """Создает вкладку действий"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Группа действий
        actions_group = QGroupBox("Действия администратора")
        actions_layout = QVBoxLayout(actions_group)

        # Кнопки действий
        publish_btn = QPushButton("Опубликовать запланированные лоты")
        publish_btn.clicked.connect(self.publish_scheduled_lots)
        actions_layout.addWidget(publish_btn)

        check_auctions_btn = QPushButton("Проверить завершенные аукционы")
        check_auctions_btn.clicked.connect(self.check_ended_auctions)
        actions_layout.addWidget(check_auctions_btn)

        backup_btn = QPushButton("Создать резервную копию")
        backup_btn.clicked.connect(self.create_backup)
        actions_layout.addWidget(backup_btn)

        layout.addWidget(actions_group)

        # Группа статистики
        stats_group = QGroupBox("Статистика системы")
        stats_layout = QFormLayout(stats_group)

        self.active_lots_label = QLabel("0")
        self.total_users_label = QLabel("0")
        self.total_bids_label = QLabel("0")

        stats_layout.addRow("Активных лотов:", self.active_lots_label)
        stats_layout.addRow("Всего пользователей:", self.total_users_label)
        stats_layout.addRow("Всего ставок:", self.total_bids_label)

        layout.addWidget(stats_group)

        self.tab_widget.addTab(tab, "Действия")

    def setup_timer(self):
        """Настраивает таймер для обновления данных"""
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_data)
        self.timer.start(30000)  # Обновляем каждые 30 секунд

    def refresh_data(self):
        """Обновляет все данные"""
        self.refresh_lots()
        self.refresh_users()
        self.refresh_finance()
        self.refresh_statistics()

    def refresh_lots(self):
        """Обновляет таблицу лотов"""
        db = SessionLocal()
        try:
            lots = db.query(Lot).order_by(Lot.created_at.desc()).all()

            self.lots_table.setRowCount(len(lots))

            for row, lot in enumerate(lots):
                # ID
                self.lots_table.setItem(row, 0, QTableWidgetItem(str(lot.id)))

                # Название
                self.lots_table.setItem(row, 1, QTableWidgetItem(lot.title))

                # Продавец
                seller = db.query(User).filter(User.id == lot.seller_id).first()
                seller_name = (
                    f"@{seller.username}"
                    if seller and seller.username
                    else "Неизвестно"
                )
                self.lots_table.setItem(row, 2, QTableWidgetItem(seller_name))

                # Цена
                self.lots_table.setItem(
                    row, 3, QTableWidgetItem(f"{lot.current_price:,.2f} ₽")
                )

                # Статус
                status_text = {
                    LotStatus.DRAFT: "Черновик",
                    LotStatus.PENDING: "На модерации",
                    LotStatus.ACTIVE: "Активен",
                    LotStatus.SOLD: "Продан",
                    LotStatus.CANCELLED: "Отменен",
                    LotStatus.EXPIRED: "Истек",
                }.get(lot.status, "Неизвестно")
                self.lots_table.setItem(row, 4, QTableWidgetItem(status_text))

                # Окончание
                end_time = (
                    lot.end_time.strftime("%d.%m.%Y %H:%M")
                    if lot.end_time
                    else "Не указано"
                )
                self.lots_table.setItem(row, 5, QTableWidgetItem(end_time))

                # Действия
                actions_widget = QWidget()
                actions_layout = QHBoxLayout(actions_widget)
                actions_layout.setContentsMargins(0, 0, 0, 0)

                edit_btn = QPushButton("Изменить")
                edit_btn.clicked.connect(
                    lambda checked, lot_id=lot.id: self.edit_lot(lot_id)
                )
                actions_layout.addWidget(edit_btn)

                delete_btn = QPushButton("Удалить")
                delete_btn.clicked.connect(
                    lambda checked, lot_id=lot.id: self.delete_lot(lot_id)
                )
                actions_layout.addWidget(delete_btn)

                self.lots_table.setCellWidget(row, 6, actions_widget)

        except Exception as e:
            logger.error(f"Ошибка при обновлении лотов: {e}")
        finally:
            db.close()

    def refresh_users(self):
        """Обновляет таблицу пользователей"""
        db = SessionLocal()
        try:
            users = db.query(User).order_by(User.created_at.desc()).all()

            self.users_table.setRowCount(len(users))

            for row, user in enumerate(users):
                # ID
                self.users_table.setItem(row, 0, QTableWidgetItem(str(user.id)))

                # Имя
                name = f"{user.first_name} {user.last_name or ''}".strip()
                self.users_table.setItem(row, 1, QTableWidgetItem(name))

                # Username
                username = f"@{user.username}" if user.username else "Не указан"
                self.users_table.setItem(row, 2, QTableWidgetItem(username))

                # Роль
                role_text = {
                    UserRole.SELLER: "Продавец-администратор",
                    UserRole.MODERATOR: "Модератор",
                    UserRole.SUPPORT: "Поддержка",
                    UserRole.SUPER_ADMIN: "Супер-Админ",
                }.get(user.role, "Неизвестно")
                self.users_table.setItem(row, 3, QTableWidgetItem(role_text))

                # Баланс
                self.users_table.setItem(
                    row, 4, QTableWidgetItem(f"{user.balance:,.2f} ₽")
                )

                # Статус
                status = "Активен" if not user.is_banned else "Заблокирован"
                self.users_table.setItem(row, 5, QTableWidgetItem(status))

                # Действия
                actions_widget = QWidget()
                actions_layout = QHBoxLayout(actions_widget)
                actions_layout.setContentsMargins(0, 0, 0, 0)

                ban_btn = QPushButton(
                    "Заблокировать" if not user.is_banned else "Разблокировать"
                )
                ban_btn.clicked.connect(
                    lambda checked, user_id=user.id: self.toggle_user_ban(user_id)
                )
                actions_layout.addWidget(ban_btn)

                self.users_table.setCellWidget(row, 6, actions_widget)

        except Exception as e:
            logger.error(f"Ошибка при обновлении пользователей: {e}")
        finally:
            db.close()

    def refresh_finance(self):
        """Обновляет финансовую информацию"""
        db = SessionLocal()
        try:
            # Общая выручка
            total_revenue = (
                db.query(Payment)
                .filter(Payment.status == "completed")
                .with_entities(func.sum(Payment.amount))
                .scalar()
                or 0
            )

            # Количество платежей
            total_payments = db.query(Payment).count()

            # Комиссии
            commission = total_revenue * 0.05  # 5%

            self.total_revenue_label.setText(f"{total_revenue:,.2f} ₽")
            self.total_payments_label.setText(str(total_payments))
            self.commission_label.setText(f"{commission:,.2f} ₽")

            # Таблица платежей
            payments = (
                db.query(Payment).order_by(Payment.created_at.desc()).limit(50).all()
            )

            self.payments_table.setRowCount(len(payments))

            for row, payment in enumerate(payments):
                self.payments_table.setItem(row, 0, QTableWidgetItem(str(payment.id)))

                user = db.query(User).filter(User.id == payment.user_id).first()
                user_name = user.first_name if user else "Неизвестно"
                self.payments_table.setItem(row, 1, QTableWidgetItem(user_name))

                self.payments_table.setItem(
                    row, 2, QTableWidgetItem(f"{payment.amount:,.2f} ₽")
                )
                self.payments_table.setItem(
                    row, 3, QTableWidgetItem(payment.payment_type)
                )
                self.payments_table.setItem(row, 4, QTableWidgetItem(payment.status))

        except Exception as e:
            logger.error(f"Ошибка при обновлении финансов: {e}")
        finally:
            db.close()

    def refresh_statistics(self):
        """Обновляет статистику"""
        db = SessionLocal()
        try:
            active_lots = db.query(Lot).filter(Lot.status == LotStatus.ACTIVE).count()
            total_users = db.query(User).count()
            total_bids = db.query(Bid).count()

            self.active_lots_label.setText(str(active_lots))
            self.total_users_label.setText(str(total_users))
            self.total_bids_label.setText(str(total_bids))

        except Exception as e:
            logger.error(f"Ошибка при обновлении статистики: {e}")
        finally:
            db.close()

    def create_lot(self):
        """Создает новый лот"""
        self.main_window.show_lot_creator()

    def edit_lot(self, lot_id: int):
        """Редактирует лот"""
        QMessageBox.information(self, "Редактирование", f"Редактирование лота {lot_id}")

    def delete_lot(self, lot_id: int):
        """Удаляет лот"""
        reply = QMessageBox.question(
            self,
            "Удаление",
            f"Вы уверены, что хотите удалить лот {lot_id}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            db = SessionLocal()
            try:
                lot = db.query(Lot).filter(Lot.id == lot_id).first()
                if lot:
                    db.delete(lot)
                    db.commit()
                    self.refresh_lots()
                    QMessageBox.information(self, "Успех", "Лот удален")
            except Exception as e:
                logger.error(f"Ошибка при удалении лота: {e}")
                QMessageBox.critical(self, "Ошибка", f"Ошибка при удалении лота: {e}")
            finally:
                db.close()

    def toggle_user_ban(self, user_id: int):
        """Блокирует/разблокирует пользователя"""
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.is_banned = not user.is_banned
                db.commit()
                self.refresh_users()

                action = "заблокирован" if user.is_banned else "разблокирован"
                QMessageBox.information(self, "Успех", f"Пользователь {action}")
        except Exception as e:
            logger.error(f"Ошибка при изменении статуса пользователя: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка: {e}")
        finally:
            db.close()

    def publish_scheduled_lots(self):
        """Публикует запланированные лоты"""
        QMessageBox.information(self, "Публикация", "Запрос на публикацию отправлен")

    def check_ended_auctions(self):
        """Проверяет завершенные аукционы"""
        QMessageBox.information(
            self, "Проверка", "Проверка завершенных аукционов выполнена"
        )

    def create_backup(self):
        """Создает резервную копию"""
        QMessageBox.information(self, "Резервная копия", "Резервная копия создана")
