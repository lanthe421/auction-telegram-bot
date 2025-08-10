"""
Главное окно системы управления аукционом
"""

import logging
import os
import sys
from datetime import datetime
from typing import Optional

# Добавляем родительскую директорию в путь Python для импорта модуля database
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from database.db import SessionLocal
from database.models import Bid, Lot, LotStatus, Payment, User, UserRole
from management.auth import AuthWindow
from management.core.lot_scheduler import lot_scheduler
from management.views.moderation_panel import ModerationPanel
from management.views.seller_panel import SellerPanel
from management.views.super_admin_panel import SuperAdminPanel
from management.views.support_panel import SupportPanel

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Главное окно системы управления"""

    def __init__(self):
        super().__init__()
        self.current_user = None
        self.auth_window = None
        self.init_ui()
        self.setup_timer()
        # Запускаем планировщик лотов
        lot_scheduler.start()
        self.show_auth()

    def closeEvent(self, event):
        """Обработчик закрытия окна"""
        # Останавливаем планировщик лотов
        lot_scheduler.stop()
        event.accept()

    def init_ui(self):
        """Инициализация интерфейса"""
        self.setWindowTitle("🏛️ Система управления аукционом")
        self.setGeometry(100, 100, 1400, 900)

        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Главный layout
        main_layout = QVBoxLayout(central_widget)

        # Заголовок
        self.header_label = QLabel("🏛️ Система управления аукционом")
        self.header_label.setFont(QFont("Segoe UI", 18, QFont.Bold))
        self.header_label.setAlignment(Qt.AlignCenter)
        self.header_label.setStyleSheet(
            """
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #2c3e50, stop:1 #3498db);
                color: white;
                padding: 15px;
                border-radius: 10px;
                margin: 5px;
            }
        """
        )
        main_layout.addWidget(self.header_label)

        # Информационная панель
        self.info_panel = self.create_info_panel()
        main_layout.addWidget(self.info_panel)

        # Основной контент
        self.content_stack = QStackedWidget()
        main_layout.addWidget(self.content_stack)

        # Создаем панели
        self.create_panels()

    def create_info_panel(self) -> QFrame:
        """Создает информационную панель"""
        panel = QFrame()
        panel.setFrameStyle(QFrame.Box)
        panel.setStyleSheet(
            """
            QFrame {
                background-color: #ecf0f1;
                border: 2px solid #bdc3c7;
                border-radius: 8px;
                padding: 10px;
            }
            QLabel {
                color: #2c3e50;
                font-size: 12px;
            }
        """
        )

        layout = QHBoxLayout(panel)

        # Информация о пользователе
        self.user_info_label = QLabel("👤 Не авторизован")
        self.user_info_label.setFont(QFont("Segoe UI", 12))
        layout.addWidget(self.user_info_label)

        layout.addStretch()

        # Время
        self.time_label = QLabel()
        self.time_label.setFont(QFont("Segoe UI", 12))
        layout.addWidget(self.time_label)

        # Кнопка выхода
        self.logout_btn = QPushButton("🚪 Выйти")
        self.logout_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """
        )
        self.logout_btn.clicked.connect(self.logout)
        self.logout_btn.hide()  # Скрываем до авторизации
        layout.addWidget(self.logout_btn)

        return panel

    def create_panels(self):
        """Создает панели для разных ролей"""
        # Панель продавца
        self.seller_panel = SellerPanel(self)
        self.content_stack.addWidget(self.seller_panel)

        # Панель модерации
        self.moderation_panel = ModerationPanel(self)
        self.content_stack.addWidget(self.moderation_panel)

        # Панель поддержки
        self.support_panel = SupportPanel(self)
        self.content_stack.addWidget(self.support_panel)

        # Панель супер-администратора
        self.super_admin_panel = SuperAdminPanel(self)
        self.content_stack.addWidget(self.super_admin_panel)

    def show_auth(self):
        """Показывает окно аутентификации"""
        if not self.auth_window:
            self.auth_window = AuthWindow()
            self.auth_window.auth_successful.connect(self.on_auth_successful)

        self.auth_window.show()
        self.hide()  # Скрываем главное окно

    def on_auth_successful(self, user_data: dict):
        """Обработка успешной авторизации"""
        self.current_user = user_data
        self.auth_window.close()
        self.auth_window = None

        # Обновляем интерфейс
        self.update_user_info()
        self.show_appropriate_panel()
        self.show()

    def show_appropriate_panel(self):
        """Показывает соответствующую панель в зависимости от роли"""
        role = self.current_user["role"]

        if role == "seller":  # Продавец-администратор
            self.content_stack.setCurrentWidget(self.seller_panel)
            self.seller_panel.refresh_data()
        elif role == "moderator":  # Модератор
            self.content_stack.setCurrentWidget(self.moderation_panel)
            self.moderation_panel.refresh_data()
        elif role == "support":  # Поддержка
            self.content_stack.setCurrentWidget(self.support_panel)
            self.support_panel.set_current_user(self.current_user)
        elif role == "super_admin":  # Супер-администратор
            self.content_stack.setCurrentWidget(self.super_admin_panel)
            self.super_admin_panel.refresh_data()
        else:
            # По умолчанию показываем панель продавца
            self.content_stack.setCurrentWidget(self.seller_panel)
            self.seller_panel.refresh_data()

    def setup_timer(self):
        """Настраивает таймер для обновления времени"""
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)  # Обновление каждую секунду

    def update_time(self):
        """Обновляет время"""
        current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        self.time_label.setText(f"🕐 {current_time}")

    def update_user_info(self):
        """Обновляет информацию о пользователе"""
        if self.current_user:
            role_text = {
                "seller": "Продавец-администратор",
                "moderator": "Модератор",
                "super_admin": "Супер-администратор",
            }.get(self.current_user["role"], "Пользователь")

            self.user_info_label.setText(
                f"👤 {self.current_user['name']} ({role_text}) | "
                f"💰 Баланс: {self.current_user['balance']:,.2f} ₽"
            )
            self.logout_btn.show()
        else:
            self.user_info_label.setText("👤 Не авторизован")
            self.logout_btn.hide()

    def logout(self):
        """Выход из системы"""
        reply = QMessageBox.question(
            self,
            "Выход",
            "Вы уверены, что хотите выйти из системы?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            self.current_user = None
            self.update_user_info()
            self.hide()
            self.show_auth()

    def get_current_user(self):
        """Возвращает текущего пользователя"""
        return self.current_user

    def refresh_system_stats(self):
        """Обновляет статистику системы (вызывается из других панелей)"""
        try:
            if hasattr(self, 'super_admin_panel'):
                self.super_admin_panel.force_refresh_stats()
                logger.info("Статистика системы обновлена из главного окна")
        except Exception as e:
            logger.error(f"Ошибка при обновлении статистики из главного окна: {e}")

    def show_message(self, title: str, message: str, icon=QMessageBox.Information):
        """Показывает сообщение пользователю"""
        QMessageBox.information(self, title, message)


def main():
    """Главная функция"""
    app = QApplication(sys.argv)

    # Устанавливаем стиль приложения
    app.setStyle("Fusion")

    # Создаем и показываем главное окно
    window = MainWindow()

    # Запускаем приложение
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
