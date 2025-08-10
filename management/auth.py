import logging
from datetime import datetime
from typing import Any, Dict, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from database.db import SessionLocal
from database.models import User, UserRole

logger = logging.getLogger(__name__)


class AuthWindow(QWidget):
    """Окно аутентификации"""

    auth_successful = pyqtSignal(dict)  # Сигнал успешной авторизации

    def __init__(self):
        super().__init__()
        self.current_user = None
        self.init_ui()

    def init_ui(self):
        """Инициализация интерфейса"""
        self.setWindowTitle("🔐 Аутентификация - Аукционная платформа")
        # Делаем окно адаптивным и прокручиваемым
        self.setMinimumSize(520, 640)
        self.resize(560, 720)
        self.setStyleSheet(
            """
            QWidget {
                background-color: #f8f9fa;
                font-family: 'Segoe UI', Arial;
            }
            QLabel {
                color: #2c3e50;
                font-size: 13px;
            }
            QLineEdit {
                padding: 8px 10px;
                border: 2px solid #e9ecef;
                border-radius: 8px;
                font-size: 13px;
                background-color: white;
            }
            QLineEdit:focus {
                border-color: #007bff;
            }
            QPushButton {
                padding: 10px 12px;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                color: white;
                background-color: #007bff;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:pressed {
                background-color: #004085;
            }
            QComboBox {
                padding: 8px 10px;
                border: 2px solid #e9ecef;
                border-radius: 8px;
                font-size: 13px;
                background-color: white;
            }
        """
        )

        # Создаем стек виджетов для переключения между формами
        self.stacked_widget = QStackedWidget()

        # Форма входа (в прокрутке)
        self.login_form = self.create_login_form()
        self.stacked_widget.addWidget(self._wrap_scroll(self.login_form))

        # Форма регистрации (в прокрутке)
        self.register_form = self.create_register_form()
        self.stacked_widget.addWidget(self._wrap_scroll(self.register_form))

        # Главный layout
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(self.stacked_widget)
        self.setLayout(layout)

    def _wrap_scroll(self, inner: QWidget) -> QScrollArea:
        """Оборачивает виджет в прокручиваемую область для компактного отображения"""
        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame)
        return scroll

    def create_login_form(self):
        """Создает форму входа"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Заголовок
        title = QLabel("🔐 Вход в систему")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setStyleSheet("color: #2c3e50; margin: 20px;")
        layout.addWidget(title)

        # Username
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText(
            "Введите ваш Telegram username (например: @username или username)"
        )
        layout.addWidget(QLabel("Telegram Username:"))
        layout.addWidget(self.username_input)

        # Подсказка для Username
        hint_label = QLabel(
            "💡 Подсказка: Введите ваш Telegram username с символом @ или без него"
        )
        hint_label.setStyleSheet("color: #6c757d; font-size: 11px; font-style: italic;")
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)

        # Роль
        self.role_combo = QComboBox()
        self.role_combo.setToolTip(
            "Выберите вашу роль для входа. Если не уверены — выберите Продавец"
        )
        self.role_combo.addItems(["Продавец", "Модератор", "Супер-администратор"])
        self.role_combo.setCurrentIndex(0)
        self.role_combo.setMinimumHeight(36)
        self.role_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        layout.addWidget(QLabel("Роль:"))
        layout.addWidget(self.role_combo)

        # Кнопки
        buttons_layout = QHBoxLayout()

        login_btn = QPushButton("Войти")
        login_btn.clicked.connect(self.login)
        buttons_layout.addWidget(login_btn)

        register_btn = QPushButton("Регистрация")
        register_btn.setStyleSheet("background-color: #28a745;")
        register_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(1))
        buttons_layout.addWidget(register_btn)

        layout.addLayout(buttons_layout)
        layout.addStretch()

        widget.setLayout(layout)
        return widget

    def create_register_form(self):
        """Создает форму регистрации"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Заголовок
        title = QLabel("📝 Регистрация")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setStyleSheet("color: #2c3e50; margin: 20px;")
        layout.addWidget(title)

        # Username
        self.reg_username_input = QLineEdit()
        self.reg_username_input.setPlaceholderText(
            "Введите ваш Telegram username (например: @username или username)"
        )
        layout.addWidget(QLabel("Telegram Username:"))
        layout.addWidget(self.reg_username_input)

        # Telegram ID
        self.reg_telegram_id_input = QLineEdit()
        self.reg_telegram_id_input.setPlaceholderText(
            "Введите ваш Telegram ID (только цифры)"
        )
        layout.addWidget(QLabel("Telegram ID:"))
        layout.addWidget(self.reg_telegram_id_input)

        # Подсказка для Username
        hint_label = QLabel(
            "💡 Подсказка: Введите ваш Telegram username с символом @ или без него"
        )
        hint_label.setStyleSheet("color: #6c757d; font-size: 11px; font-style: italic;")
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)

        # Имя
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Введите ваше имя")
        layout.addWidget(QLabel("Имя:"))
        layout.addWidget(self.name_input)

        # Фамилия
        self.lastname_input = QLineEdit()
        self.lastname_input.setPlaceholderText("Введите вашу фамилию")
        layout.addWidget(QLabel("Фамилия:"))
        layout.addWidget(self.lastname_input)

        # Телефон
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("+7 (999) 123-45-67")
        layout.addWidget(QLabel("Телефон:"))
        layout.addWidget(self.phone_input)

        # Кнопки
        buttons_layout = QHBoxLayout()

        register_btn = QPushButton("Зарегистрироваться")
        register_btn.clicked.connect(self.register)
        buttons_layout.addWidget(register_btn)

        back_btn = QPushButton("Назад")
        back_btn.setStyleSheet("background-color: #6c757d;")
        back_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        buttons_layout.addWidget(back_btn)

        layout.addLayout(buttons_layout)
        layout.addStretch()

        widget.setLayout(layout)
        return widget

    def login(self):
        """Обработка входа в систему"""
        username_text = self.username_input.text().strip()
        role_text = self.role_combo.currentText()

        if not username_text:
            QMessageBox.warning(self, "Ошибка", "Введите Telegram username")
            return

        # Обрабатываем username (убираем @ если есть)
        username = username_text.lstrip("@")

        # Определяем роль
        role_map = {
            "Продавец": UserRole.SELLER,
            "Модератор": UserRole.MODERATOR,
            "Супер-администратор": UserRole.SUPER_ADMIN,
        }
        role = role_map.get(role_text, UserRole.SELLER)

        db = SessionLocal()
        try:
            # Ищем пользователя по username
            user = db.query(User).filter(User.username == username).first()

            if user:
                # Проверяем, заблокирован ли пользователь
                if user.is_banned:
                    QMessageBox.critical(
                        self,
                        "Доступ запрещен",
                        f"Пользователь @{username} заблокирован администратором.\n"
                        f"Обратитесь к администратору для разблокировки аккаунта.",
                    )
                    return

                # Проверяем, соответствует ли роль
                if user.role == role:
                    self.current_user = {
                        "id": user.id,
                        "telegram_id": user.telegram_id,
                        "username": user.username,
                        "name": f"{user.first_name} {user.last_name or ''}".strip(),
                        "role": user.role.value,
                        "balance": user.balance,
                    }
                    self.auth_successful.emit(self.current_user)
                    self.close()
                else:
                    # Показываем доступные роли для этого пользователя
                    role_names = {
                        UserRole.SELLER: "Продавец-администратор",
                        UserRole.MODERATOR: "Модератор",
                        UserRole.SUPER_ADMIN: "Супер-администратор",
                    }
                    actual_role = role_names.get(user.role, "Неизвестно")
                    QMessageBox.warning(
                        self,
                        "Ошибка роли",
                        f"Пользователь с Telegram username @{username} найден, но его роль: {actual_role}\n"
                        f"Выберите правильную роль для входа.",
                    )
            else:
                QMessageBox.warning(
                    self,
                    "Пользователь не найден",
                    f"Пользователь с Telegram username @{username} не найден в системе.\n"
                    f"Используйте регистрацию для создания нового аккаунта.",
                )

        except Exception as e:
            logger.error(f"Ошибка при входе: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка при входе: {e}")
        finally:
            db.close()

    def register(self):
        """Обработка регистрации"""
        username_text = self.reg_username_input.text().strip()
        telegram_id_text = self.reg_telegram_id_input.text().strip()
        name = self.name_input.text().strip()
        lastname = self.lastname_input.text().strip()
        phone = self.phone_input.text().strip()

        if not all([username_text, telegram_id_text, name]):
            QMessageBox.warning(
                self,
                "Ошибка",
                "Заполните обязательные поля (Telegram Username, Telegram ID и имя)",
            )
            return

        # Обрабатываем username (убираем @ если есть)
        username = username_text.lstrip("@")

        # Валидируем Telegram ID
        if not telegram_id_text.isdigit():
            QMessageBox.warning(
                self, "Ошибка", "Telegram ID должен содержать только цифры"
            )
            return
        telegram_id = int(telegram_id_text)
        if telegram_id <= 0:
            QMessageBox.warning(self, "Ошибка", "Укажите корректный Telegram ID")
            return

        db = SessionLocal()
        try:
            # Проверяем, не существует ли уже пользователь
            existing_user = db.query(User).filter(User.username == username).first()
            if existing_user:
                if existing_user.is_banned:
                    QMessageBox.critical(
                        self,
                        "Доступ запрещен",
                        f"Пользователь с Telegram username @{username} заблокирован администратором.\n"
                        f"Регистрация с этим username невозможна.",
                    )
                else:
                    QMessageBox.warning(
                        self,
                        "Пользователь уже существует",
                        f"Пользователь с Telegram username @{username} уже зарегистрирован в системе.\n"
                        f"Используйте вход в систему для авторизации.",
                    )
                return

            # Создаем нового пользователя (по умолчанию продавец-администратор)
            new_user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=name,
                last_name=lastname,
                phone=phone,
                role=UserRole.SELLER,
                balance=0.0,
            )

            db.add(new_user)
            db.commit()

            QMessageBox.information(
                self,
                "Регистрация успешна",
                f"Пользователь {name} успешно зарегистрирован!\n\n"
                f"📋 Данные для входа:\n"
                f"• Telegram Username: @{username}\n"
                f"• Роль: Продавец-администратор\n\n"
                f"Теперь вы можете войти в систему.",
            )

            # Очищаем поля и переключаемся на форму входа
            self.reg_username_input.clear()
            self.reg_telegram_id_input.clear()
            self.name_input.clear()
            self.lastname_input.clear()
            self.phone_input.clear()
            self.stacked_widget.setCurrentIndex(0)

        except Exception as e:
            logger.error(f"Ошибка при регистрации: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка при регистрации: {e}")
        finally:
            db.close()
