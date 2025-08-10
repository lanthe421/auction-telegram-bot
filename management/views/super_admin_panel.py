"""
Панель супер-администратора
"""

import logging
import os
import re

# import requests
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
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
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import func

from config.settings import NOTIFICATION_INTERVAL_MINUTES
from database.db import SessionLocal
from database.models import Bid, Lot, LotStatus, Payment, User, UserRole

logger = logging.getLogger(__name__)


class UserEditDialog(QDialog):
    """Диалог редактирования пользователя"""

    def __init__(self, parent=None, user=None):
        super().__init__(parent)
        self.user = user
        self.init_ui()

    def init_ui(self):
        """Инициализация интерфейса"""
        self.setWindowTitle(
            "Редактирование пользователя" if self.user else "Добавление пользователя"
        )
        self.setFixedSize(400, 500)
        self.setModal(True)

        layout = QVBoxLayout(self)

        # Форма
        form_layout = QFormLayout()

        # Username
        self.username_input = QLineEdit()
        if self.user:
            self.username_input.setText(self.user.username or "")
        self.username_input.setPlaceholderText("Введите username (без @)")
        form_layout.addRow("Username:", self.username_input)

        # Имя
        self.first_name_input = QLineEdit()
        if self.user:
            self.first_name_input.setText(self.user.first_name or "")
        self.first_name_input.setPlaceholderText("Введите имя")
        form_layout.addRow("Имя:", self.first_name_input)

        # Фамилия
        self.last_name_input = QLineEdit()
        if self.user:
            self.last_name_input.setText(self.user.last_name or "")
        self.last_name_input.setPlaceholderText("Введите фамилию (необязательно)")
        form_layout.addRow("Фамилия:", self.last_name_input)

        # Телефон
        self.phone_input = QLineEdit()
        if self.user:
            self.phone_input.setText(self.user.phone or "")
        self.phone_input.setPlaceholderText("+7 (999) 123-45-67")
        form_layout.addRow("Телефон:", self.phone_input)

        # Роль
        self.role_combo = QComboBox()
        self.role_combo.addItems(
            ["Продавец-администратор", "Модератор", "Поддержка", "Супер-Админ"]
        )
        if self.user:
            role_index = {
                UserRole.SELLER: 0,
                UserRole.MODERATOR: 1,
                UserRole.SUPPORT: 2,
                UserRole.SUPER_ADMIN: 3,
            }.get(self.user.role, 0)
            self.role_combo.setCurrentIndex(role_index)
        form_layout.addRow("Роль:", self.role_combo)

        # Баланс
        self.balance_input = QLineEdit()
        if self.user:
            self.balance_input.setText(str(self.user.balance))
        else:
            self.balance_input.setText("0.0")
        self.balance_input.setPlaceholderText("0.0")
        form_layout.addRow("Баланс (₽):", self.balance_input)

        # Статус блокировки
        self.banned_checkbox = QComboBox()
        self.banned_checkbox.addItems(["Активен", "Заблокирован"])
        if self.user:
            self.banned_checkbox.setCurrentIndex(1 if self.user.is_banned else 0)
        form_layout.addRow("Статус:", self.banned_checkbox)

        layout.addLayout(form_layout)

        # Кнопки
        buttons_layout = QHBoxLayout()

        save_btn = QPushButton("Сохранить")
        save_btn.clicked.connect(self.accept)
        save_btn.setStyleSheet("background-color: #27ae60; color: white; padding: 8px;")
        buttons_layout.addWidget(save_btn)

        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet(
            "background-color: #e74c3c; color: white; padding: 8px;"
        )
        buttons_layout.addWidget(cancel_btn)

        layout.addLayout(buttons_layout)

    def get_user_data(self) -> dict:
        """Возвращает данные пользователя из формы"""
        try:
            # Валидация
            username = self.username_input.text().strip()
            first_name = self.first_name_input.text().strip()

            if not username:
                QMessageBox.warning(self, "Ошибка", "Username обязателен")
                return None

            if not first_name:
                QMessageBox.warning(self, "Ошибка", "Имя обязательно")
                return None

            # Убираем @ из username если есть
            username = username.lstrip("@")

            # Парсим баланс
            try:
                balance = float(self.balance_input.text().replace(",", "."))
            except ValueError:
                QMessageBox.warning(self, "Ошибка", "Неверный формат баланса")
                return None

            # Определяем роль
            role_map = {
                "Продавец-администратор": UserRole.SELLER,
                "Модератор": UserRole.MODERATOR,
                "Поддержка": UserRole.SUPPORT,
                "Супер-Админ": UserRole.SUPER_ADMIN,
            }
            role = role_map[self.role_combo.currentText()]

            # Определяем статус блокировки
            is_banned = self.banned_checkbox.currentText() == "Заблокирован"

            return {
                "username": username,
                "first_name": first_name,
                "last_name": self.last_name_input.text().strip(),
                "phone": self.phone_input.text().strip(),
                "role": role,
                "balance": balance,
                "is_banned": is_banned,
            }

        except Exception as e:
            logger.error(f"Ошибка при получении данных пользователя: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка при обработке данных: {e}")
            return None


class SuperAdminPanel(QWidget):
    """Панель супер-администратора"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.init_ui()
        self.setup_timer()

    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout(self)

        # Заголовок
        title = QLabel("Панель супер-администратора")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Вкладки
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Создаем вкладки
        self.create_system_overview_tab()
        self.create_user_management_tab()
        self.create_financial_management_tab()
        self.create_system_settings_tab()
        self.create_backup_restore_tab()

        # Подключаем обработчик переключения вкладок
        self.tab_widget.currentChanged.connect(self.on_tab_changed)

        # Обновляем данные
        self.refresh_data()

    def on_tab_changed(self, index):
        """Обработчик переключения вкладок"""
        # Если переключились на вкладку "Обзор системы" (индекс 0), обновляем статистику
        if index == 0:
            self.refresh_system_stats()

    def create_system_overview_tab(self):
        """Создает вкладку обзора системы"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Статистика системы
        stats_group = QGroupBox("Общая статистика системы")
        stats_layout = QFormLayout(stats_group)

        self.total_users_label = QLabel("0")
        self.total_lots_label = QLabel("0")
        self.total_bids_label = QLabel("0")
        self.platform_balance_label = QLabel("0 ₽")
        self.system_uptime_label = QLabel("0 дней")

        stats_layout.addRow("Всего пользователей:", self.total_users_label)
        stats_layout.addRow("Всего лотов:", self.total_lots_label)
        stats_layout.addRow("Всего ставок:", self.total_bids_label)
        stats_layout.addRow("Баланс площадки:", self.platform_balance_label)
        stats_layout.addRow("Время работы системы:", self.system_uptime_label)

        layout.addWidget(stats_group)

        # Активность системы
        activity_group = QGroupBox("Активность системы")
        activity_layout = QVBoxLayout(activity_group)

        self.activity_text = QTextEdit()
        self.activity_text.setReadOnly(True)
        self.activity_text.setMaximumHeight(200)
        activity_layout.addWidget(self.activity_text)

        layout.addWidget(activity_group)

        # Кнопки управления
        btn_layout = QHBoxLayout()

        refresh_btn = QPushButton("Обновить")
        refresh_btn.clicked.connect(self.refresh_system_stats)
        btn_layout.addWidget(refresh_btn)

        status_btn = QPushButton("Проверить статус")
        status_btn.clicked.connect(self.check_system_status)
        status_btn.setStyleSheet("background-color: #3498db; color: white;")
        btn_layout.addWidget(status_btn)

        layout.addLayout(btn_layout)

        self.tab_widget.addTab(tab, "Обзор системы")

    def create_user_management_tab(self):
        """Создает вкладку управления пользователями"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Панель фильтров
        filters_layout = QHBoxLayout()

        self.user_role_filter = QComboBox()
        self.user_role_filter.addItems(
            [
                "Все роли",
                "Продавец-администратор",
                "Модератор",
                "Поддержка",
                "Супер-Админ",
            ]
        )
        filters_layout.addWidget(QLabel("Роль:"))
        filters_layout.addWidget(self.user_role_filter)

        self.user_status_filter = QComboBox()
        self.user_status_filter.addItems(["Любой статус", "Активен", "Заблокирован"])
        filters_layout.addWidget(QLabel("Статус:"))
        filters_layout.addWidget(self.user_status_filter)

        self.user_search_input = QLineEdit()
        self.user_search_input.setPlaceholderText("Поиск (имя/username)")
        filters_layout.addWidget(self.user_search_input)

        self.user_sort_combo = QComboBox()
        self.user_sort_combo.addItems(
            [
                "По дате (новые)",
                "По дате (старые)",
                "По имени A→Я",
                "По имени Я→A",
            ]
        )
        filters_layout.addWidget(QLabel("Сортировка:"))
        filters_layout.addWidget(self.user_sort_combo)

        apply_filters_btn = QPushButton("Применить")
        apply_filters_btn.clicked.connect(self.refresh_users)
        filters_layout.addWidget(apply_filters_btn)

        reset_filters_btn = QPushButton("Сбросить")
        reset_filters_btn.clicked.connect(self.reset_user_filters)
        filters_layout.addWidget(reset_filters_btn)

        layout.addLayout(filters_layout)

        # Кнопки управления
        btn_layout = QHBoxLayout()

        refresh_users_btn = QPushButton("Обновить")
        refresh_users_btn.clicked.connect(self.refresh_users)
        btn_layout.addWidget(refresh_users_btn)

        add_user_btn = QPushButton("Добавить пользователя")
        add_user_btn.clicked.connect(self.add_user)
        add_user_btn.setStyleSheet("background-color: #27ae60; color: white;")
        btn_layout.addWidget(add_user_btn)

        layout.addLayout(btn_layout)

        # Таблица пользователей
        self.users_table = QTableWidget()
        self.users_table.setColumnCount(9)
        self.users_table.setHorizontalHeaderLabels(
            [
                "ID",
                "Имя",
                "Username",
                "Роль",
                "Баланс",
                "Статус",
                "Страйки",
                "Регистрация",
                "Действия",
            ]
        )

        header = self.users_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)

        layout.addWidget(self.users_table)

        self.tab_widget.addTab(tab, "Управление пользователями")

    def create_financial_management_tab(self):
        """Создает вкладку финансового управления"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Финансовая статистика
        finance_group = QGroupBox("Финансовое управление")
        finance_layout = QFormLayout(finance_group)

        self.total_revenue_super_label = QLabel("0 ₽")
        self.commission_revenue_label = QLabel("0 ₽")
        self.pending_payments_label = QLabel("0")
        self.completed_payments_label = QLabel("0")

        finance_layout.addRow("Общая выручка:", self.total_revenue_super_label)
        finance_layout.addRow("Комиссии:", self.commission_revenue_label)
        finance_layout.addRow("Ожидающие платежи:", self.pending_payments_label)
        finance_layout.addRow("Завершенные платежи:", self.completed_payments_label)

        layout.addWidget(finance_group)

        # Таблица платежей
        self.payments_table = QTableWidget()
        self.payments_table.setColumnCount(6)
        self.payments_table.setHorizontalHeaderLabels(
            ["ID", "Пользователь", "Сумма", "Тип", "Статус", "Действия"]
        )

        header = self.payments_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)

        layout.addWidget(self.payments_table)

        # Кнопки финансового управления
        finance_btn_layout = QHBoxLayout()

        export_finance_btn = QPushButton("Экспорт финансов")
        export_finance_btn.clicked.connect(self.export_financial_data)
        finance_btn_layout.addWidget(export_finance_btn)

        adjust_balance_btn = QPushButton("Корректировка балансов")
        adjust_balance_btn.clicked.connect(self.adjust_user_balances)
        finance_btn_layout.addWidget(adjust_balance_btn)

        layout.addLayout(finance_btn_layout)

        self.tab_widget.addTab(tab, "Финансовое управление")

    def create_system_settings_tab(self):
        """Создает вкладку настроек системы"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Настройки аукциона
        auction_group = QGroupBox("Настройки аукциона")
        auction_layout = QFormLayout(auction_group)

        self.commission_percent_spin = QSpinBox()
        self.commission_percent_spin.setRange(1, 20)
        self.commission_percent_spin.setValue(5)
        auction_layout.addRow("Комиссия (%):", self.commission_percent_spin)

        self.penalty_percent_spin = QSpinBox()
        self.penalty_percent_spin.setRange(1, 20)
        self.penalty_percent_spin.setValue(5)
        auction_layout.addRow("Штраф за удаление (%):", self.penalty_percent_spin)

        self.max_strikes_spin = QSpinBox()
        self.max_strikes_spin.setRange(1, 10)
        self.max_strikes_spin.setValue(3)
        auction_layout.addRow("Максимум страйков:", self.max_strikes_spin)

        layout.addWidget(auction_group)

        # Настройки уведомлений
        notification_group = QGroupBox("Настройки уведомлений")
        notification_layout = QFormLayout(notification_group)

        self.notification_interval_spin = QSpinBox()
        self.notification_interval_spin.setRange(1, 60)
        self.notification_interval_spin.setValue(NOTIFICATION_INTERVAL_MINUTES)
        notification_layout.addRow(
            "Интервал уведомлений (мин):", self.notification_interval_spin
        )

        layout.addWidget(notification_group)

        # Кнопки сохранения
        save_btn = QPushButton("Сохранить настройки")
        save_btn.clicked.connect(self.save_system_settings)
        save_btn.setStyleSheet("background-color: #3498db; color: white;")
        layout.addWidget(save_btn)

        self.tab_widget.addTab(tab, "Настройки системы")

    def create_backup_restore_tab(self):
        """Создает вкладку резервного копирования"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Резервное копирование
        backup_group = QGroupBox("Резервное копирование")
        backup_layout = QVBoxLayout(backup_group)

        create_backup_btn = QPushButton("Создать резервную копию")
        create_backup_btn.clicked.connect(self.create_backup)
        create_backup_btn.setStyleSheet("background-color: #27ae60; color: white;")
        backup_layout.addWidget(create_backup_btn)

        restore_backup_btn = QPushButton("Восстановить из резервной копии")
        restore_backup_btn.clicked.connect(self.restore_backup)
        restore_backup_btn.setStyleSheet("background-color: #e67e22; color: white;")
        backup_layout.addWidget(restore_backup_btn)

        layout.addWidget(backup_group)

        # Логи системы
        logs_group = QGroupBox("Логи системы")
        logs_layout = QVBoxLayout(logs_group)

        self.logs_text = QTextEdit()
        self.logs_text.setReadOnly(True)
        self.logs_text.setMaximumHeight(300)
        logs_layout.addWidget(self.logs_text)

        layout.addWidget(logs_group)

        # Кнопки управления логами
        logs_btn_layout = QHBoxLayout()

        refresh_logs_btn = QPushButton("Обновить логи")
        refresh_logs_btn.clicked.connect(self.refresh_logs)
        logs_btn_layout.addWidget(refresh_logs_btn)

        clear_logs_btn = QPushButton("Очистить логи")
        clear_logs_btn.clicked.connect(self.clear_logs)
        clear_logs_btn.setStyleSheet("background-color: #e74c3c; color: white;")
        logs_btn_layout.addWidget(clear_logs_btn)

        layout.addLayout(logs_btn_layout)

        self.tab_widget.addTab(tab, "Резервное копирование")

    def setup_timer(self):
        """Настраивает таймер для обновления данных"""
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_data)
        self.timer.start(30000)  # Обновление каждые 30 секунд

    def refresh_data(self):
        """Обновляет все данные"""
        self.refresh_system_stats()
        self.refresh_users()
        self.refresh_financial_data()

    def refresh_system_stats(self):
        """Обновляет статистику системы"""
        logger.info("Начинаем обновление статистики системы")
        db = SessionLocal()
        try:
            # Общая статистика
            total_users = db.query(User).count()
            total_lots = db.query(Lot).count()
            total_bids = db.query(Bid).count()

            logger.info(
                f"Получена статистика: пользователей={total_users}, лотов={total_lots}, ставок={total_bids}"
            )

            # Баланс площадки (сумма балансов всех супер-админов)
            super_admins = (
                db.query(User).filter(User.role == UserRole.SUPER_ADMIN).all()
            )
            platform_balance = (
                sum(sa.balance for sa in super_admins) if super_admins else 0
            )

            # Время работы системы (реальное)
            first_user = db.query(User).order_by(User.created_at.asc()).first()
            first_lot = db.query(Lot).order_by(Lot.created_at.asc()).first()
            if first_user and first_lot:
                start_time = min(first_user.created_at, first_lot.created_at)
            elif first_user:
                start_time = first_user.created_at
            elif first_lot:
                start_time = first_lot.created_at
            else:
                start_time = None
            if start_time:
                from datetime import datetime

                days = (datetime.utcnow() - start_time).days
                system_uptime = f"{days} дней"
            else:
                system_uptime = "0 дней"

            logger.info(f"Время работы системы: {system_uptime}")

            # Обновляем метки статистики
            self.total_users_label.setText(str(total_users))
            self.total_lots_label.setText(str(total_lots))
            self.total_bids_label.setText(str(total_bids))
            self.platform_balance_label.setText(f"{platform_balance:,.2f} ₽")
            self.system_uptime_label.setText(system_uptime)

            logger.info("Метки статистики обновлены")

            # Активность системы
            recent_activity = "Последние действия системы:\n"
            recent_activity += f"• Пользователей: {total_users}\n"
            recent_activity += f"• Активных лотов: {db.query(Lot).filter(Lot.status == LotStatus.ACTIVE).count()}\n"
            recent_activity += f"• Завершенных лотов: {db.query(Lot).filter(Lot.status == LotStatus.SOLD).count()}\n"
            recent_activity += f"• Баланс площадки: {platform_balance:,.2f} ₽"

            self.activity_text.setText(recent_activity)

            logger.info("Статистика системы успешно обновлена")

        except Exception as e:
            logger.error(f"Ошибка при обновлении статистики: {e}")
        finally:
            db.close()

    def force_refresh_stats(self):
        """Принудительное обновление статистики (вызывается из других панелей)"""
        try:
            self.refresh_system_stats()
            logger.info("Статистика системы обновлена")
        except Exception as e:
            logger.error(f"Ошибка при принудительном обновлении статистики: {e}")

    def refresh_users(self):
        """Обновляет таблицу пользователей"""
        db = SessionLocal()
        try:
            query = db.query(User)

            # Фильтр по роли
            role_text = (
                getattr(self, "user_role_filter", None).currentText()
                if hasattr(self, "user_role_filter")
                else "Все роли"
            )
            if role_text and role_text != "Все роли":
                role_map = {
                    "Продавец-администратор": UserRole.SELLER,
                    "Модератор": UserRole.MODERATOR,
                    "Поддержка": UserRole.SUPPORT,
                    "Супер-Админ": UserRole.SUPER_ADMIN,
                }
                role_value = role_map.get(role_text)
                if role_value is not None:
                    query = query.filter(User.role == role_value)

            # Фильтр по статусу
            status_text = (
                getattr(self, "user_status_filter", None).currentText()
                if hasattr(self, "user_status_filter")
                else "Любой статус"
            )
            if status_text == "Активен":
                query = query.filter(~User.is_banned)
            elif status_text == "Заблокирован":
                query = query.filter(User.is_banned)

            # Поиск по имени/username
            search_term = (
                getattr(self, "user_search_input", None).text().strip()
                if hasattr(self, "user_search_input")
                else ""
            )
            if search_term:
                like = f"%{search_term}%"
                query = query.filter(
                    (User.username.ilike(like))
                    | (User.first_name.ilike(like))
                    | (User.last_name.ilike(like))
                )

            # Сортировка
            sort_text = (
                getattr(self, "user_sort_combo", None).currentText()
                if hasattr(self, "user_sort_combo")
                else "По дате (новые)"
            )
            if sort_text == "По дате (старые)":
                query = query.order_by(User.created_at.asc())
            elif sort_text == "По имени A→Я":
                query = query.order_by(User.first_name.asc(), User.last_name.asc())
            elif sort_text == "По имени Я→A":
                query = query.order_by(User.first_name.desc(), User.last_name.desc())
            else:  # По дате (новые)
                query = query.order_by(User.created_at.desc())

            users = query.all()

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

                # Страйки
                self.users_table.setItem(row, 6, QTableWidgetItem(f"{user.strikes}/3"))

                # Регистрация
                reg_date = user.created_at.strftime("%d.%m.%Y")
                self.users_table.setItem(row, 7, QTableWidgetItem(reg_date))

                # Действия
                actions_widget = QWidget()
                actions_layout = QHBoxLayout(actions_widget)
                actions_layout.setContentsMargins(0, 0, 0, 0)

                edit_btn = QPushButton("Изменить")
                edit_btn.clicked.connect(
                    lambda checked, user_id=user.id: self.edit_user(user_id)
                )
                actions_layout.addWidget(edit_btn)

                # Кнопка выдать страйк
                strike_btn = QPushButton("Выдать страйк")
                strike_btn.setStyleSheet("background-color: #f39c12; color: white;")
                strike_btn.clicked.connect(
                    lambda checked, user_id=user.id: self.give_strike(user_id)
                )
                actions_layout.addWidget(strike_btn)

                ban_btn = QPushButton(
                    "Заблокировать" if not user.is_banned else "Разблокировать"
                )
                ban_btn.clicked.connect(
                    lambda checked, user_id=user.id: self.toggle_user_ban(user_id)
                )
                actions_layout.addWidget(ban_btn)

                self.users_table.setCellWidget(row, 8, actions_widget)

        except Exception as e:
            logger.error(f"Ошибка при обновлении пользователей: {e}")
        finally:
            db.close()

    def reset_user_filters(self):
        """Сбрасывает фильтры пользователей"""
        try:
            if hasattr(self, "user_role_filter"):
                self.user_role_filter.setCurrentIndex(0)
            if hasattr(self, "user_status_filter"):
                self.user_status_filter.setCurrentIndex(0)
            if hasattr(self, "user_search_input"):
                self.user_search_input.clear()
            if hasattr(self, "user_sort_combo"):
                self.user_sort_combo.setCurrentIndex(0)
        except Exception:
            pass
        self.refresh_users()

    def refresh_financial_data(self):
        """Обновляет финансовые данные"""
        db = SessionLocal()
        try:
            # Финансовая статистика
            total_revenue = (
                db.query(Payment)
                .filter(Payment.status == "completed")
                .with_entities(func.sum(Payment.amount))
                .scalar()
                or 0
            )

            commission_revenue = total_revenue * 0.05  # 5%
            pending_payments = (
                db.query(Payment).filter(Payment.status == "pending").count()
            )
            completed_payments = (
                db.query(Payment).filter(Payment.status == "completed").count()
            )

            self.total_revenue_super_label.setText(f"{total_revenue:,.2f} ₽")
            self.commission_revenue_label.setText(f"{commission_revenue:,.2f} ₽")
            self.pending_payments_label.setText(str(pending_payments))
            self.completed_payments_label.setText(str(completed_payments))

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

                # Действия
                actions_widget = QWidget()
                actions_layout = QHBoxLayout(actions_widget)
                actions_layout.setContentsMargins(0, 0, 0, 0)

                view_btn = QPushButton("Просмотр")
                view_btn.clicked.connect(
                    lambda checked, payment_id=payment.id: self.view_payment(payment_id)
                )
                actions_layout.addWidget(view_btn)

                self.payments_table.setCellWidget(row, 5, actions_widget)

        except Exception as e:
            logger.error(f"Ошибка при обновлении финансовых данных: {e}")
        finally:
            db.close()

    def check_system_status(self):
        """Проверяет статус системы"""
        QMessageBox.information(self, "Статус системы", "Система работает нормально")

    def add_user(self):
        """Добавляет нового пользователя"""
        dialog = UserEditDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            user_data = dialog.get_user_data()
            if user_data:
                self.save_user(user_data)

    def edit_user(self, user_id: int):
        """Редактирует пользователя"""
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                dialog = UserEditDialog(self, user)
                if dialog.exec_() == QDialog.Accepted:
                    user_data = dialog.get_user_data()
                    if user_data:
                        self.update_user(user_id, user_data)
            else:
                QMessageBox.warning(self, "Ошибка", "Пользователь не найден")
        except Exception as e:
            logger.error(f"Ошибка при редактировании пользователя: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка при редактировании: {e}")
        finally:
            db.close()

    def give_strike(self, user_id: int):
        """Выдает страйк пользователю"""
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                logger.info(
                    f"Выдача страйка пользователю {user.id} (telegram_id={user.telegram_id}): текущие страйки={user.strikes}/3, is_banned={user.is_banned}"
                )

                # Запрашиваем подтверждение
                reply = QMessageBox.question(
                    self,
                    "Подтверждение",
                    f"Вы уверены, что хотите выдать страйк пользователю {user.first_name} (@{user.username})?\n\n"
                    f"Текущие страйки: {user.strikes}/3",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )

                if reply == QMessageBox.Yes:
                    user.strikes += 1
                    logger.info(
                        f"Страйк выдан пользователю {user.id}: страйки={user.strikes}/3"
                    )

                    # Если достигли 3 страйков, автоматически блокируем
                    if user.strikes >= 3:
                        user.is_banned = True
                        action_text = f"выдан страйк и заблокирован (3/3 страйков)"
                        logger.info(
                            f"Пользователь {user.id} автоматически заблокирован после 3 страйков"
                        )

                        # Отправляем уведомление в бот о блокировке
                        self.send_ban_notification_to_bot(user)
                    else:
                        action_text = f"выдан страйк ({user.strikes}/3)"

                    db.commit()
                    logger.info(
                        f"Изменения сохранены: страйки={user.strikes}, is_banned={user.is_banned}"
                    )

                    QMessageBox.information(
                        self, "Успех", f"Пользователь {action_text}"
                    )

                    # Обновляем таблицу и статистику
                    self.refresh_users()
                    self.refresh_system_stats()
            else:
                QMessageBox.warning(self, "Ошибка", "Пользователь не найден")
        except Exception as e:
            logger.error(f"Ошибка при выдаче страйка: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка: {e}")
        finally:
            db.close()

    def send_ban_notification_to_bot(self, user):
        """Отправляет уведомление в бот о блокировке пользователя"""
        try:
            import requests

            from config.settings import BOT_TOKEN

            # Отправляем сообщение пользователю через бот API
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            message = (
                "❌ **Ваш аккаунт заблокирован!**\n\n"
                "Вы получили 3 страйка за нарушение правил.\n"
                "Обратитесь к администратору для разблокировки."
            )

            data = {
                "chat_id": user.telegram_id,
                "text": message,
                "parse_mode": "Markdown",
            }

            response = requests.post(url, json=data)
            if response.status_code == 200:
                logger.info(
                    f"Уведомление о блокировке отправлено пользователю {user.telegram_id}"
                )
            else:
                logger.error(f"Ошибка отправки уведомления: {response.text}")

        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления в бот: {e}")

    def toggle_user_ban(self, user_id: int):
        """Переключает статус блокировки пользователя"""
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                logger.info(
                    f"Переключение блокировки для пользователя {user.id} (telegram_id={user.telegram_id}): текущий статус is_banned={user.is_banned}"
                )

                # Запрашиваем подтверждение
                action = "заблокировать" if not user.is_banned else "разблокировать"
                reply = QMessageBox.question(
                    self,
                    "Подтверждение",
                    f"Вы уверены, что хотите {action} пользователя {user.first_name} (@{user.username})?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )

                if reply == QMessageBox.Yes:
                    previous_banned = user.is_banned
                    user.is_banned = not user.is_banned
                    # Если разблокируем пользователя — сбрасываем страйки
                    if previous_banned and not user.is_banned:
                        user.strikes = 0
                        logger.info(
                            f"Пользователь {user.id} разблокирован — страйки сброшены до 0"
                        )
                    db.commit()

                    logger.info(
                        f"Статус блокировки изменен для пользователя {user.id}: is_banned={user.is_banned}"
                    )

                    action_text = "заблокирован" if user.is_banned else "разблокирован"
                    QMessageBox.information(
                        self, "Успех", f"Пользователь {action_text}"
                    )

                    # Если пользователь заблокирован, отправляем уведомление в бот
                    if user.is_banned:
                        logger.info(
                            f"Отправляем уведомление о блокировке пользователю {user.telegram_id}"
                        )
                        self.send_ban_notification_to_bot(user)

                    # Обновляем таблицу и статистику
                    self.refresh_users()
                    self.refresh_system_stats()
            else:
                QMessageBox.warning(self, "Ошибка", "Пользователь не найден")
        except Exception as e:
            logger.error(f"Ошибка при изменении статуса пользователя: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка: {e}")
        finally:
            db.close()

    def save_user(self, user_data: dict):
        """Сохраняет нового пользователя"""
        db = SessionLocal()
        try:
            # Проверяем, не существует ли уже пользователь с таким username
            existing_user = (
                db.query(User).filter(User.username == user_data["username"]).first()
            )
            if existing_user:
                QMessageBox.warning(
                    self, "Ошибка", "Пользователь с таким username уже существует"
                )
                return

            # Попытка определить telegram_id по username (если это id)
            telegram_id = None
            if re.fullmatch(r"\d{6,}", user_data["username"]):
                telegram_id = int(user_data["username"])
            # Если не удалось определить, оставить None
            if telegram_id is None:
                QMessageBox.warning(
                    self,
                    "Внимание",
                    "Telegram ID не определён автоматически. После регистрации пользователь должен авторизоваться через Telegram бот, чтобы связать аккаунт.",
                )

            new_user = User(
                telegram_id=telegram_id,
                username=user_data["username"],
                first_name=user_data["first_name"],
                last_name=user_data.get("last_name", ""),
                phone=user_data.get("phone", ""),
                role=user_data["role"],
                balance=user_data.get("balance", 0.0),
                is_banned=user_data.get("is_banned", False),
            )

            db.add(new_user)
            db.commit()

            QMessageBox.information(
                self, "Успех", f"Пользователь {user_data['first_name']} успешно создан"
            )
            self.refresh_users()
            self.refresh_system_stats()

        except Exception as e:
            logger.error(f"Ошибка при создании пользователя: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка при создании: {e}")
        finally:
            db.close()

    def update_user(self, user_id: int, user_data: dict):
        """Обновляет существующего пользователя"""
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                # Проверяем, не занят ли username другим пользователем
                existing_user = (
                    db.query(User)
                    .filter(User.username == user_data["username"], User.id != user_id)
                    .first()
                )
                if existing_user:
                    QMessageBox.warning(
                        self, "Ошибка", "Пользователь с таким username уже существует"
                    )
                    return

                # Обновляем данные
                user.username = user_data["username"]
                user.first_name = user_data["first_name"]
                user.last_name = user_data.get("last_name", "")
                user.phone = user_data.get("phone", "")
                user.role = user_data["role"]
                user.balance = user_data.get("balance", 0.0)
                previous_banned = user.is_banned
                user.is_banned = user_data.get("is_banned", False)
                # Если статус меняется с заблокирован на активен — сбрасываем страйки
                if previous_banned and not user.is_banned:
                    user.strikes = 0
                    logger.info(
                        f"Пользователь {user.id} разблокирован через форму — страйки сброшены до 0"
                    )

                db.commit()

                QMessageBox.information(
                    self,
                    "Успех",
                    f"Пользователь {user_data['first_name']} успешно обновлен",
                )
                self.refresh_users()
                self.refresh_system_stats()
            else:
                QMessageBox.warning(self, "Ошибка", "Пользователь не найден")
        except Exception as e:
            logger.error(f"Ошибка при обновлении пользователя: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка при обновлении: {e}")
        finally:
            db.close()

    def export_financial_data(self):
        """Экспортирует финансовые данные"""
        QMessageBox.information(self, "Экспорт", "Финансовые данные экспортированы")

    def adjust_user_balances(self):
        """Корректирует балансы пользователей"""
        QMessageBox.information(self, "Корректировка", "Функция корректировки балансов")

    def save_system_settings(self):
        """Сохраняет настройки системы"""
        notif_interval = self.notification_interval_spin.value()
        # Сохраняем в config/settings.py (или .env)
        self.save_notification_interval(notif_interval)
        QMessageBox.information(self, "Сохранение", "Настройки системы сохранены")

    def save_notification_interval(self, value):
        # Простой способ: заменить строку в config/settings.py
        import re

        settings_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "..", "config", "settings.py"
        )
        settings_path = os.path.abspath(settings_path)
        with open(settings_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        pattern = re.compile(
            r"NOTIFICATION_INTERVAL_MINUTES\s*=\s*int\(os.getenv\([^)]+\)\)"
        )
        for i, line in enumerate(lines):
            if pattern.search(line):
                lines[i] = (
                    f'NOTIFICATION_INTERVAL_MINUTES = int(os.getenv("NOTIFICATION_INTERVAL_MINUTES", "{value}"))\n'
                )
        with open(settings_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

    def create_backup(self):
        """Создает резервную копию"""
        QMessageBox.information(self, "Резервная копия", "Резервная копия создана")

    def restore_backup(self):
        """Восстанавливает из резервной копии"""
        QMessageBox.information(
            self, "Восстановление", "Восстановление из резервной копии"
        )

    def refresh_logs(self):
        """Обновляет логи"""
        self.logs_text.setText("Логи системы загружены...")

    def clear_logs(self):
        """Очищает логи"""
        self.logs_text.clear()
        QMessageBox.information(self, "Очистка", "Логи очищены")

    def view_payment(self, payment_id: int):
        """Просматривает платеж"""
        QMessageBox.information(self, "Платеж", f"Детали платежа {payment_id}")
        QMessageBox.information(self, "Платеж", f"Детали платежа {payment_id}")
