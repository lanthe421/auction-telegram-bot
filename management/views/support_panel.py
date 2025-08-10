#!/usr/bin/env python3
"""
Панель поддержки для модераторов
"""

import os
import sys
from datetime import datetime
from typing import List, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# Добавляем путь к проекту
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from database.db import SessionLocal
from database.models import SupportQuestion, User


class SupportPanel(QWidget):
    """Панель поддержки для модераторов"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.current_user = None
        self.current_question: Optional[SupportQuestion] = None
        self.init_ui()
        self.load_questions()

        # Таймер для автообновления
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.load_questions)
        self.update_timer.start(30000)  # Обновляем каждые 30 секунд

    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout()

        # Заголовок
        title = QLabel("📞 Панель поддержки")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Сплиттер для разделения списка вопросов и ответа
        splitter = QSplitter(Qt.Horizontal)

        # Левая панель - список вопросов
        left_panel = self.create_questions_panel()
        splitter.addWidget(left_panel)

        # Правая панель - ответ на вопрос
        right_panel = self.create_answer_panel()
        splitter.addWidget(right_panel)

        # Устанавливаем пропорции
        splitter.setSizes([400, 600])
        layout.addWidget(splitter)

        self.setLayout(layout)

    def set_current_user(self, user_data: dict):
        """Устанавливает текущего пользователя"""
        self.current_user = user_data

    def create_questions_panel(self) -> QWidget:
        """Создает панель со списком вопросов"""
        panel = QWidget()
        layout = QVBoxLayout()

        # Заголовок
        header = QLabel("📋 Вопросы пользователей")
        header.setFont(QFont("Arial", 12, QFont.Bold))
        layout.addWidget(header)

        # Фильтры
        filter_layout = QHBoxLayout()

        self.status_filter = QComboBox()
        self.status_filter.addItems(["Все", "Ожидают ответа", "Отвечены", "Закрыты"])
        self.status_filter.currentTextChanged.connect(self.apply_filters)
        filter_layout.addWidget(QLabel("Статус:"))
        filter_layout.addWidget(self.status_filter)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Поиск по тексту вопроса...")
        self.search_input.textChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.search_input)

        layout.addLayout(filter_layout)

        # Таблица вопросов
        self.questions_table = QTableWidget()
        self.questions_table.setColumnCount(5)
        self.questions_table.setHorizontalHeaderLabels(
            ["ID", "Пользователь", "Дата", "Статус", "Вопрос"]
        )

        # Настройка таблицы
        header = self.questions_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # ID
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Пользователь
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Дата
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Статус
        header.setSectionResizeMode(4, QHeaderView.Stretch)  # Вопрос

        self.questions_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.questions_table.setAlternatingRowColors(True)
        self.questions_table.itemSelectionChanged.connect(self.on_question_selected)

        layout.addWidget(self.questions_table)

        # Кнопки управления
        buttons_layout = QHBoxLayout()

        refresh_btn = QPushButton("🔄 Обновить")
        refresh_btn.clicked.connect(self.load_questions)
        buttons_layout.addWidget(refresh_btn)

        buttons_layout.addStretch()

        layout.addLayout(buttons_layout)

        panel.setLayout(layout)
        return panel

    def create_answer_panel(self) -> QWidget:
        """Создает панель для ответа на вопрос"""
        panel = QWidget()
        layout = QVBoxLayout()

        # Заголовок
        self.answer_header = QLabel("💬 Ответ на вопрос")
        self.answer_header.setFont(QFont("Arial", 12, QFont.Bold))
        layout.addWidget(self.answer_header)

        # Информация о вопросе
        self.question_info = QLabel("Выберите вопрос из списка")
        self.question_info.setWordWrap(True)
        self.question_info.setStyleSheet(
            "background-color: #f0f0f0; padding: 10px; border-radius: 5px;"
        )
        layout.addWidget(self.question_info)

        # Текст вопроса
        question_label = QLabel("📝 Вопрос:")
        question_label.setFont(QFont("Arial", 10, QFont.Bold))
        layout.addWidget(question_label)

        self.question_text = QTextEdit()
        self.question_text.setReadOnly(True)
        self.question_text.setMaximumHeight(100)
        layout.addWidget(self.question_text)

        # Поле для ответа
        answer_label = QLabel("✍️ Ваш ответ:")
        answer_label.setFont(QFont("Arial", 10, QFont.Bold))
        layout.addWidget(answer_label)

        self.answer_text = QTextEdit()
        self.answer_text.setPlaceholderText("Введите ваш ответ пользователю...")
        layout.addWidget(self.answer_text)

        # Кнопки действий
        buttons_layout = QHBoxLayout()

        self.send_answer_btn = QPushButton("📤 Отправить ответ")
        self.send_answer_btn.clicked.connect(self.send_answer)
        self.send_answer_btn.setEnabled(False)
        buttons_layout.addWidget(self.send_answer_btn)

        self.close_question_btn = QPushButton("🔒 Закрыть вопрос")
        self.close_question_btn.clicked.connect(self.close_question)
        self.close_question_btn.setEnabled(False)
        buttons_layout.addWidget(self.close_question_btn)

        clear_btn = QPushButton("🗑️ Очистить")
        clear_btn.clicked.connect(self.clear_answer)
        buttons_layout.addWidget(clear_btn)

        layout.addLayout(buttons_layout)

        # История ответов
        history_label = QLabel("📚 История ответов:")
        history_label.setFont(QFont("Arial", 10, QFont.Bold))
        layout.addWidget(history_label)

        self.answer_history = QTextEdit()
        self.answer_history.setReadOnly(True)
        self.answer_history.setMaximumHeight(150)
        layout.addWidget(self.answer_history)

        panel.setLayout(layout)
        return panel

    def load_questions(self):
        """Загружает вопросы из базы данных"""
        db = SessionLocal()
        try:
            # Получаем все вопросы
            questions = (
                db.query(SupportQuestion)
                .order_by(SupportQuestion.created_at.desc())
                .all()
            )

            self.questions_table.setRowCount(len(questions))

            for row, question in enumerate(questions):
                # Получаем пользователя
                user = db.query(User).filter(User.id == question.user_id).first()
                user_name = user.first_name if user else "Неизвестно"

                # ID
                id_item = QTableWidgetItem(str(question.id))
                id_item.setData(Qt.UserRole, question.id)
                self.questions_table.setItem(row, 0, id_item)

                # Пользователь
                self.questions_table.setItem(row, 1, QTableWidgetItem(user_name))

                # Дата
                date_str = question.created_at.strftime("%d.%m.%Y %H:%M")
                self.questions_table.setItem(row, 2, QTableWidgetItem(date_str))

                # Статус
                status_item = QTableWidgetItem(self.get_status_text(question.status))
                status_item.setData(Qt.UserRole, question.status)
                self.set_status_color(status_item, question.status)
                self.questions_table.setItem(row, 3, status_item)

                # Вопрос (обрезанный)
                question_preview = (
                    question.question[:50] + "..."
                    if len(question.question) > 50
                    else question.question
                )
                self.questions_table.setItem(row, 4, QTableWidgetItem(question_preview))

            # Применяем фильтры
            self.apply_filters()

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить вопросы: {e}")
        finally:
            db.close()

    def apply_filters(self):
        """Применяет фильтры к таблице"""
        status_filter = self.status_filter.currentText()
        search_text = self.search_input.text().lower()

        for row in range(self.questions_table.rowCount()):
            show_row = True

            # Фильтр по статусу
            if status_filter != "Все":
                status_item = self.questions_table.item(row, 3)
                if status_item and status_item.data(Qt.UserRole) != self.get_status_key(
                    status_filter
                ):
                    show_row = False

            # Фильтр по поиску
            if search_text:
                question_item = self.questions_table.item(row, 4)
                if question_item and search_text not in question_item.text().lower():
                    show_row = False

            self.questions_table.setRowHidden(row, not show_row)

    def get_status_text(self, status: str) -> str:
        """Возвращает текст статуса"""
        status_map = {
            "pending": "Ожидает ответа",
            "answered": "Отвечен",
            "closed": "Закрыт",
        }
        return status_map.get(status, status)

    def get_status_key(self, status_text: str) -> str:
        """Возвращает ключ статуса по тексту"""
        status_map = {
            "Ожидает ответа": "pending",
            "Отвечены": "answered",
            "Закрыты": "closed",
        }
        return status_map.get(status_text, "")

    def set_status_color(self, item: QTableWidgetItem, status: str):
        """Устанавливает цвет для статуса"""
        colors = {
            "pending": QColor(255, 193, 7),  # Желтый
            "answered": QColor(40, 167, 69),  # Зеленый
            "closed": QColor(108, 117, 125),  # Серый
        }

        if status in colors:
            item.setBackground(colors[status])
            item.setForeground(QColor(0, 0, 0))

    def on_question_selected(self):
        """Обработчик выбора вопроса"""
        current_row = self.questions_table.currentRow()
        if current_row >= 0:
            question_id = int(self.questions_table.item(current_row, 0).text())
            self.load_question_details(question_id)
        else:
            self.clear_question_details()

    def load_question_details(self, question_id: int):
        """Загружает детали выбранного вопроса"""
        db = SessionLocal()
        try:
            question = (
                db.query(SupportQuestion)
                .filter(SupportQuestion.id == question_id)
                .first()
            )
            if not question:
                return

            self.current_question = question

            # Получаем пользователя
            user = db.query(User).filter(User.id == question.user_id).first()
            user_name = user.first_name if user else "Неизвестно"

            # Обновляем заголовок
            self.answer_header.setText(f"💬 Ответ на вопрос #{question_id}")

            # Обновляем информацию о вопросе
            info_text = f"""
<b>👤 Пользователь:</b> {user_name}<br>
<b>📅 Дата:</b> {question.created_at.strftime('%d.%m.%Y %H:%M')}<br>
<b>📊 Статус:</b> {self.get_status_text(question.status)}
            """.strip()
            self.question_info.setText(info_text)

            # Обновляем текст вопроса
            self.question_text.setText(question.question)

            # Очищаем поле ответа
            self.answer_text.clear()

            # Загружаем историю ответов
            self.load_answer_history(question)

            # Включаем/выключаем кнопки
            can_answer = question.status == "pending"
            self.send_answer_btn.setEnabled(can_answer)
            self.close_question_btn.setEnabled(question.status != "closed")

        except Exception as e:
            QMessageBox.critical(
                self, "Ошибка", f"Не удалось загрузить детали вопроса: {e}"
            )
        finally:
            db.close()

    def load_answer_history(self, question: SupportQuestion):
        """Загружает историю ответов"""
        if not question.answer:
            self.answer_history.setText("Нет ответов")
            return

        history_text = f"""
<b>📝 Ответ:</b><br>
{question.answer}<br><br>
<b>⏰ Время ответа:</b> {question.answered_at.strftime('%d.%m.%Y %H:%M') if question.answered_at else 'Не указано'}
        """.strip()

        self.answer_history.setText(history_text)

    def clear_question_details(self):
        """Очищает детали вопроса"""
        self.current_question = None
        self.answer_header.setText("💬 Ответ на вопрос")
        self.question_info.setText("Выберите вопрос из списка")
        self.question_text.clear()
        self.answer_text.clear()
        self.answer_history.clear()
        self.send_answer_btn.setEnabled(False)
        self.close_question_btn.setEnabled(False)

    def send_answer(self):
        """Отправляет ответ на вопрос"""
        if not self.current_question:
            return

        answer_text = self.answer_text.toPlainText().strip()
        if not answer_text:
            QMessageBox.warning(self, "Предупреждение", "Введите текст ответа")
            return

        db = SessionLocal()
        try:
            # Получаем ID текущего пользователя из базы данных
            db = SessionLocal()
            current_user_db = (
                db.query(User)
                .filter(User.telegram_id == self.current_user["telegram_id"])
                .first()
            )

            # Обновляем вопрос
            self.current_question.answer = answer_text
            self.current_question.status = "answered"
            self.current_question.answered_by = (
                current_user_db.id if current_user_db else None
            )
            self.current_question.answered_at = datetime.utcnow()

            db.commit()

            # Отправляем ответ пользователю через Telegram
            self.send_telegram_answer(answer_text)

            QMessageBox.information(self, "Успех", "Ответ отправлен пользователю")

            # Обновляем интерфейс
            self.load_questions()
            self.load_question_details(self.current_question.id)

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось отправить ответ: {e}")
        finally:
            db.close()

    def send_telegram_answer(self, answer_text: str):
        """Отправляет ответ пользователю через Telegram"""
        try:
            # Получаем telegram_id пользователя
            db = SessionLocal()
            user = (
                db.query(User).filter(User.id == self.current_question.user_id).first()
            )
            if not user:
                return

            # Импортируем бота
            import asyncio

            from bot.main import bot

            # Создаем сообщение
            message_text = f"""
📞 **Ответ на ваш вопрос #{self.current_question.id}**

{answer_text}

---
💬 Для нового вопроса используйте /support
            """.strip()

            # Отправляем сообщение
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    bot.send_message(
                        chat_id=user.telegram_id,
                        text=message_text,
                        parse_mode="Markdown",
                    )
                )
            finally:
                loop.close()

        except Exception as e:
            print(f"Ошибка при отправке Telegram сообщения: {e}")
        finally:
            db.close()

    def close_question(self):
        """Закрывает вопрос"""
        if not self.current_question:
            return

        reply = QMessageBox.question(
            self,
            "Подтверждение",
            "Вы уверены, что хотите закрыть этот вопрос?",
            QMessageBox.Yes | QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            db = SessionLocal()
            try:
                self.current_question.status = "closed"
                db.commit()

                QMessageBox.information(self, "Успех", "Вопрос закрыт")

                # Обновляем интерфейс
                self.load_questions()
                self.load_question_details(self.current_question.id)

            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось закрыть вопрос: {e}")
            finally:
                db.close()

    def clear_answer(self):
        """Очищает поле ответа"""
        self.answer_text.clear()

    def closeEvent(self, event):
        """Обработчик закрытия окна"""
        self.update_timer.stop()
        super().closeEvent(event)
