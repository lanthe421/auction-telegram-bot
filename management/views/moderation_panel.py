"""
Панель модерации
"""

import logging
from datetime import datetime, timedelta

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from database.db import SessionLocal
from database.models import Bid, Complaint, Lot, LotStatus, SupportQuestion, User
from management.utils.document_utils import (
    DocumentGenerator,
    ImageManager,
    format_local_time,
)

logger = logging.getLogger(__name__)


class LotDetailDialog(QDialog):
    """Красивый диалог для просмотра деталей лота"""

    def __init__(self, lot: Lot, parent=None):
        super().__init__(parent)
        self.lot = lot
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(f"📦 Детали лота: {self.lot.title}")
        self.setMinimumSize(800, 700)
        self.setStyleSheet(
            """
            QDialog {
                background-color: #f8f9fa;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #dee2e6;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #495057;
            }
            QLabel {
                color: #212529;
            }
            QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """
        )

        layout = QVBoxLayout()

        # Создаем скроллируемую область
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()

        # Основная информация о лоте
        info_group = QGroupBox("📋 Основная информация")
        info_layout = QFormLayout()

        # ID лота с красивым оформлением
        id_label = QLabel(f"#{self.lot.id}")
        id_label.setStyleSheet(
            """
            QLabel {
                background-color: #e9ecef;
                padding: 5px 10px;
                border-radius: 15px;
                font-weight: bold;
                color: #495057;
            }
        """
        )
        info_layout.addRow("ID лота:", id_label)

        # Название
        title_label = QLabel(self.lot.title)
        title_label.setStyleSheet(
            """
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #212529;
                padding: 5px;
                background-color: #f8f9fa;
                border-radius: 4px;
            }
        """
        )
        info_layout.addRow("Название:", title_label)

        # Описание
        description_label = QLabel(self.lot.description or "Описание не указано")
        description_label.setWordWrap(True)
        description_label.setStyleSheet(
            """
            QLabel {
                padding: 10px;
                background-color: #f8f9fa;
                border-radius: 5px;
                border-left: 4px solid #007bff;
            }
        """
        )
        info_layout.addRow("Описание:", description_label)

        # Цены
        price_layout = QHBoxLayout()

        starting_price_label = QLabel(f"{self.lot.starting_price:,.2f} ₽")
        starting_price_label.setStyleSheet(
            """
            QLabel {
                background-color: #d4edda;
                color: #155724;
                padding: 8px 12px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
        """
        )
        price_layout.addWidget(QLabel("Стартовая цена:"))
        price_layout.addWidget(starting_price_label)

        current_price_label = QLabel(f"{self.lot.current_price:,.2f} ₽")
        current_price_label.setStyleSheet(
            """
            QLabel {
                background-color: #cce5ff;
                color: #004085;
                padding: 8px 12px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
        """
        )
        price_layout.addWidget(QLabel("Текущая цена:"))
        price_layout.addWidget(current_price_label)

        info_layout.addRow("Цены:", price_layout)

        # Статус с цветовым кодированием
        status_text = {
            LotStatus.DRAFT: "Черновик",
            LotStatus.PENDING: "На модерации",
            LotStatus.ACTIVE: "Активен",
            LotStatus.SOLD: "Продан",
            LotStatus.CANCELLED: "Отменен",
            LotStatus.EXPIRED: "Истек",
        }.get(self.lot.status, "Неизвестно")

        status_label = QLabel(status_text)
        status_style = {
            LotStatus.PENDING: "background-color: #fff3cd; color: #856404;",
            LotStatus.ACTIVE: "background-color: #d4edda; color: #155724;",
            LotStatus.SOLD: "background-color: #d1ecf1; color: #0c5460;",
            LotStatus.CANCELLED: "background-color: #f8d7da; color: #721c24;",
            LotStatus.EXPIRED: "background-color: #e2e3e5; color: #383d41;",
        }.get(self.lot.status, "")

        status_label.setStyleSheet(
            f"""
            QLabel {{
                {status_style}
                padding: 8px 12px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }}
        """
        )
        info_layout.addRow("Статус:", status_label)

        info_group.setLayout(info_layout)
        scroll_layout.addWidget(info_group)

        # Информация о продавце
        seller_group = QGroupBox("👤 Информация о продавце")
        seller_layout = QFormLayout()

        db = SessionLocal()
        try:
            seller = db.query(User).filter(User.id == self.lot.seller_id).first()
            seller_name = (
                f"@{seller.username}" if seller and seller.username else "Неизвестно"
            )
            seller_balance = f"{seller.balance:,.2f} ₽" if seller else "Неизвестно"
        except:
            seller_name = "Неизвестно"
            seller_balance = "Неизвестно"
        finally:
            db.close()

        seller_name_label = QLabel(seller_name)
        seller_name_label.setStyleSheet(
            """
            QLabel {
                background-color: #e9ecef;
                padding: 5px 10px;
                border-radius: 4px;
                font-weight: bold;
            }
        """
        )
        seller_layout.addRow("Username:", seller_name_label)

        seller_balance_label = QLabel(seller_balance)
        seller_balance_label.setStyleSheet(
            """
            QLabel {
                background-color: #f8f9fa;
                padding: 5px 10px;
                border-radius: 4px;
            }
        """
        )
        seller_layout.addRow("Баланс:", seller_balance_label)

        seller_group.setLayout(seller_layout)
        scroll_layout.addWidget(seller_group)

        # Временная информация
        time_group = QGroupBox("⏰ Временная информация")
        time_layout = QFormLayout()

        created_label = QLabel(format_local_time(self.lot.created_at))
        created_label.setStyleSheet(
            """
            QLabel {
                background-color: #f8f9fa;
                padding: 5px 10px;
                border-radius: 4px;
            }
        """
        )
        time_layout.addRow("Создан:", created_label)

        start_time_label = QLabel(format_local_time(self.lot.start_time))
        start_time_label.setStyleSheet(
            """
            QLabel {
                background-color: #d4edda;
                padding: 5px 10px;
                border-radius: 4px;
                font-weight: bold;
            }
        """
        )
        time_layout.addRow("Время старта:", start_time_label)

        end_time_label = QLabel(format_local_time(self.lot.end_time))
        end_time_label.setStyleSheet(
            """
            QLabel {
                background-color: #f8d7da;
                padding: 5px 10px;
                border-radius: 4px;
                font-weight: bold;
            }
        """
        )
        time_layout.addRow("Время окончания:", end_time_label)

        time_group.setLayout(time_layout)
        scroll_layout.addWidget(time_group)

        # Дополнительная информация
        extra_group = QGroupBox("📄 Дополнительная информация")
        extra_layout = QFormLayout()

        doc_type = (
            self.lot.document_type.value if self.lot.document_type else "Стандартный"
        )
        doc_type_label = QLabel(doc_type)
        doc_type_label.setStyleSheet(
            """
            QLabel {
                background-color: #e9ecef;
                padding: 5px 10px;
                border-radius: 4px;
            }
        """
        )
        extra_layout.addRow("Тип документа:", doc_type_label)

        if self.lot.location:
            location_label = QLabel(self.lot.location)
            location_label.setStyleSheet(
                """
                QLabel {
                    background-color: #f8f9fa;
                    padding: 5px 10px;
                    border-radius: 4px;
                }
            """
            )
            extra_layout.addRow("Геолокация:", location_label)

        if self.lot.seller_link:
            link_label = QLabel(self.lot.seller_link)
            link_label.setStyleSheet(
                """
                QLabel {
                    background-color: #cce5ff;
                    padding: 5px 10px;
                    border-radius: 4px;
                    color: #004085;
                }
            """
            )
            extra_layout.addRow("Ссылка продавца:", link_label)

        extra_group.setLayout(extra_layout)
        scroll_layout.addWidget(extra_group)

        # Изображения лота
        images_data = ImageManager.get_lot_images(self.lot)
        if images_data:
            images_group = QGroupBox("🖼️ Изображения лота")
            images_layout = QVBoxLayout()

            for i, image_path in enumerate(images_data):
                try:
                    from pathlib import Path

                    if Path(image_path).exists():
                        image_label = QLabel()
                        pixmap = QPixmap(image_path)
                        if not pixmap.isNull():
                            # Масштабируем изображение
                            scaled_pixmap = pixmap.scaled(
                                400, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation
                            )
                            image_label.setPixmap(scaled_pixmap)
                            image_label.setAlignment(Qt.AlignCenter)
                            image_label.setStyleSheet(
                                "QLabel { border: 2px solid #dee2e6; border-radius: 8px; padding: 10px; background-color: white; }"
                            )
                            images_layout.addWidget(image_label)
                        else:
                            images_layout.addWidget(
                                QLabel(f"Ошибка загрузки изображения {i+1}")
                            )
                    else:
                        images_layout.addWidget(QLabel(f"Файл не найден: {image_path}"))
                except Exception as e:
                    images_layout.addWidget(
                        QLabel(f"Ошибка загрузки изображения {i+1}: {e}")
                    )

            images_group.setLayout(images_layout)
            scroll_layout.addWidget(images_group)

        # Статистика ставок
        db = SessionLocal()
        try:
            bids = db.query(Bid).filter(Bid.lot_id == self.lot.id).all()
            if bids:
                bids_group = QGroupBox("💰 Статистика ставок")
                bids_layout = QFormLayout()

                total_bids = len(bids)
                max_bid = max([bid.amount for bid in bids]) if bids else 0
                unique_bidders = len(set([bid.bidder_id for bid in bids]))

                total_bids_label = QLabel(str(total_bids))
                total_bids_label.setStyleSheet(
                    """
                    QLabel {
                        background-color: #d4edda;
                        color: #155724;
                        padding: 5px 10px;
                        border-radius: 4px;
                        font-weight: bold;
                    }
                """
                )
                bids_layout.addRow("Всего ставок:", total_bids_label)

                max_bid_label = QLabel(f"{max_bid:,.2f} ₽")
                max_bid_label.setStyleSheet(
                    """
                    QLabel {
                        background-color: #cce5ff;
                        color: #004085;
                        padding: 5px 10px;
                        border-radius: 4px;
                        font-weight: bold;
                    }
                """
                )
                bids_layout.addRow("Максимальная ставка:", max_bid_label)

                unique_bidders_label = QLabel(str(unique_bidders))
                unique_bidders_label.setStyleSheet(
                    """
                    QLabel {
                        background-color: #fff3cd;
                        color: #856404;
                        padding: 5px 10px;
                        border-radius: 4px;
                        font-weight: bold;
                    }
                """
                )
                bids_layout.addRow("Уникальных участников:", unique_bidders_label)

                # Показываем последние ставки
                recent_bids = sorted(bids, key=lambda x: x.created_at, reverse=True)[:5]
                if recent_bids:
                    bids_layout.addRow("", QLabel(""))  # Пустая строка
                    bids_layout.addRow("Последние ставки:", QLabel(""))
                    for i, bid in enumerate(recent_bids):
                        bid_text = f"{i+1}. {bid.amount:,.2f} ₽ ({format_local_time(bid.created_at)})"
                        bid_label = QLabel(bid_text)
                        bid_label.setStyleSheet(
                            """
                            QLabel {
                                background-color: #f8f9fa;
                                padding: 3px 8px;
                                border-radius: 3px;
                                margin: 2px;
                            }
                        """
                        )
                        bids_layout.addRow("", bid_label)

                bids_group.setLayout(bids_layout)
                scroll_layout.addWidget(bids_group)
        except Exception as e:
            logger.error(f"Ошибка при загрузке ставок: {e}")
        finally:
            db.close()

        scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        # Кнопки действий
        buttons_layout = QHBoxLayout()

        # Кнопка экспорта
        export_btn = QPushButton("📄 Экспорт")
        export_btn.clicked.connect(self.export_lot)
        buttons_layout.addWidget(export_btn)

        buttons_layout.addStretch()

        # Кнопка закрытия
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #545b62;
            }
        """
        )
        buttons_layout.addWidget(close_btn)

        layout.addLayout(buttons_layout)

        self.setLayout(layout)

    def export_lot(self):
        """Экспорт лота в различные форматы"""
        try:
            pass

            # Предлагаем сохранить файл
            file_dialog = QFileDialog()
            file_dialog.setNameFilter("Текстовый файл (*.txt);;HTML файл (*.html)")
            file_dialog.setDefaultSuffix("txt")
            file_dialog.setAcceptMode(QFileDialog.AcceptSave)

            if file_dialog.exec_():
                file_path = file_dialog.selectedFiles()[0]

                # Определяем формат по расширению
                format_type = "html" if file_path.endswith(".html") else "txt"
                content = DocumentGenerator.generate_lot_report(self.lot, format_type)

                # Сохраняем файл
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)

                QMessageBox.information(
                    self, "Успех", f"Лот экспортирован в файл:\n{file_path}"
                )

        except Exception as e:
            logger.error(f"Ошибка при экспорте лота: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка при экспорте: {e}")


class ModerationPanel(QWidget):
    """Панель модерации"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.init_ui()
        self.setup_timer()

    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout(self)

        # Заголовок
        title = QLabel("Панель модерации")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Вкладки
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Создаем вкладки
        self.create_lots_moderation_tab()
        self.create_complaints_tab()
        self.create_support_tab()
        self.create_statistics_tab()

        # Обновляем данные
        self.refresh_data()

    def create_lots_moderation_tab(self):
        """Создает вкладку модерации лотов"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Кнопки управления
        btn_layout = QHBoxLayout()

        refresh_btn = QPushButton("Обновить")
        refresh_btn.clicked.connect(self.refresh_pending_lots)
        btn_layout.addWidget(refresh_btn)

        approve_all_btn = QPushButton("Одобрить все")
        approve_all_btn.clicked.connect(self.approve_all_lots)
        approve_all_btn.setStyleSheet(
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
        btn_layout.addWidget(approve_all_btn)

        layout.addLayout(btn_layout)

        # Таблица лотов на модерации
        self.pending_lots_table = QTableWidget()
        self.pending_lots_table.setColumnCount(8)
        self.pending_lots_table.setHorizontalHeaderLabels(
            [
                "ID",
                "Название",
                "Продавец",
                "Цена",
                "Тип документа",
                "Создан",
                "Время начала",
                "Действия",
            ]
        )

        header = self.pending_lots_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)

        layout.addWidget(self.pending_lots_table)

        self.tab_widget.addTab(tab, "Модерация лотов")

    def create_complaints_tab(self):
        """Создает вкладку жалоб"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Кнопки управления
        btn_layout = QHBoxLayout()

        refresh_complaints_btn = QPushButton("Обновить")
        refresh_complaints_btn.clicked.connect(self.refresh_complaints)
        btn_layout.addWidget(refresh_complaints_btn)

        layout.addLayout(btn_layout)

        # Таблица жалоб
        self.complaints_table = QTableWidget()
        self.complaints_table.setColumnCount(7)
        self.complaints_table.setHorizontalHeaderLabels(
            ["ID", "Жалобщик", "Причина", "Описание", "Статус", "Дата", "Действия"]
        )

        header = self.complaints_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)

        layout.addWidget(self.complaints_table)

        self.tab_widget.addTab(tab, "Жалобы")

    def create_support_tab(self):
        """Создает вкладку поддержки"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Кнопки управления
        btn_layout = QHBoxLayout()

        refresh_support_btn = QPushButton("Обновить")
        refresh_support_btn.clicked.connect(self.refresh_support_questions)
        btn_layout.addWidget(refresh_support_btn)

        layout.addLayout(btn_layout)

        # Таблица вопросов поддержки
        self.support_questions_table = QTableWidget()
        self.support_questions_table.setColumnCount(8)
        self.support_questions_table.setHorizontalHeaderLabels(
            [
                "ID",
                "Пользователь",
                "Вопрос",
                "Статус",
                "Дата создания",
                "Ответил",
                "Дата ответа",
                "Действия",
            ]
        )

        header = self.support_questions_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)

        layout.addWidget(self.support_questions_table)

        self.tab_widget.addTab(tab, "Поддержка")

    def create_statistics_tab(self):
        """Создает вкладку статистики модерации"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Статистика модерации
        stats_group = QGroupBox("Статистика модерации")
        stats_layout = QFormLayout(stats_group)

        self.pending_lots_count = QLabel("0")
        self.approved_lots_count = QLabel("0")
        self.rejected_lots_count = QLabel("0")
        self.pending_complaints_count = QLabel("0")
        self.resolved_complaints_count = QLabel("0")

        stats_layout.addRow("Лотов на модерации:", self.pending_lots_count)
        stats_layout.addRow("Одобренных лотов:", self.approved_lots_count)
        stats_layout.addRow("Отклоненных лотов:", self.rejected_lots_count)
        stats_layout.addRow("Жалоб на рассмотрении:", self.pending_complaints_count)
        stats_layout.addRow("Решенных жалоб:", self.resolved_complaints_count)

        layout.addWidget(stats_group)

        # Детальная статистика
        detail_group = QGroupBox("Детальная статистика")
        detail_layout = QVBoxLayout(detail_group)

        self.moderation_stats_text = QTextEdit()
        self.moderation_stats_text.setReadOnly(True)
        self.moderation_stats_text.setMaximumHeight(200)
        detail_layout.addWidget(self.moderation_stats_text)

        layout.addWidget(detail_group)

        self.tab_widget.addTab(tab, "Статистика")

    def setup_timer(self):
        """Настраивает таймер для обновления данных"""
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_data)
        self.timer.start(30000)  # Обновляем каждые 30 секунд

    def refresh_data(self):
        """Обновляет все данные"""
        self.refresh_pending_lots()
        self.refresh_complaints()
        self.refresh_support_questions()
        self.refresh_statistics()

    def refresh_pending_lots(self):
        """Обновляет таблицу лотов на модерации"""
        db = SessionLocal()
        try:
            # Получаем лоты на модерации с сортировкой по приоритету
            # Сначала лоты без времени начала (для немедленного одобрения)
            # Затем лоты с запланированным временем
            pending_lots = (
                db.query(Lot)
                .filter(Lot.status == LotStatus.PENDING)
                .order_by(
                    Lot.start_time.is_(None).desc(),  # Сначала лоты без start_time
                    Lot.start_time.asc(),  # Затем по времени начала
                )
                .all()
            )

            self.pending_lots_table.setRowCount(len(pending_lots))

            for row, lot in enumerate(pending_lots):
                # Определяем приоритет для цветового выделения
                is_immediate = lot.start_time is None

                # ID
                id_item = QTableWidgetItem(str(lot.id))
                if is_immediate:
                    id_item.setBackground(Qt.yellow)  # Выделяем срочные лоты
                self.pending_lots_table.setItem(row, 0, id_item)

                # Название
                title_item = QTableWidgetItem(lot.title)
                if is_immediate:
                    title_item.setBackground(Qt.yellow)
                self.pending_lots_table.setItem(row, 1, title_item)

                # Продавец
                seller = db.query(User).filter(User.id == lot.seller_id).first()
                seller_name = (
                    f"@{seller.username}"
                    if seller and seller.username
                    else "Неизвестно"
                )
                seller_item = QTableWidgetItem(seller_name)
                if is_immediate:
                    seller_item.setBackground(Qt.yellow)
                self.pending_lots_table.setItem(row, 2, seller_item)

                # Цена
                price_item = QTableWidgetItem(f"{lot.starting_price:,.2f} ₽")
                if is_immediate:
                    price_item.setBackground(Qt.yellow)
                self.pending_lots_table.setItem(row, 3, price_item)

                # Тип документа
                doc_type = (
                    lot.document_type.value if lot.document_type else "Стандартный"
                )
                doc_item = QTableWidgetItem(doc_type)
                if is_immediate:
                    doc_item.setBackground(Qt.yellow)
                self.pending_lots_table.setItem(row, 4, doc_item)

                # Дата создания
                created_date = format_local_time(lot.created_at)
                created_item = QTableWidgetItem(created_date)
                if is_immediate:
                    created_item.setBackground(Qt.yellow)
                self.pending_lots_table.setItem(row, 5, created_item)

                # Время начала
                start_time_str = (
                    format_local_time(lot.start_time)
                    if lot.start_time
                    else "Немедленно"
                )
                start_item = QTableWidgetItem(start_time_str)
                if is_immediate:
                    start_item.setBackground(Qt.yellow)
                    start_item.setForeground(Qt.red)  # Красный текст для срочных
                self.pending_lots_table.setItem(row, 6, start_item)

                # Действия
                actions_widget = QWidget()
                actions_layout = QHBoxLayout(actions_widget)
                actions_layout.setContentsMargins(0, 0, 0, 0)

                approve_btn = QPushButton("Одобрить")
                approve_btn.clicked.connect(
                    lambda checked, lot_id=lot.id: self.approve_lot(lot_id)
                )
                if is_immediate:
                    approve_btn.setStyleSheet(
                        "background-color: #e74c3c; color: white; font-weight: bold;"
                    )
                    approve_btn.setText("Одобрить срочно")
                else:
                    approve_btn.setStyleSheet(
                        "background-color: #27ae60; color: white;"
                    )
                actions_layout.addWidget(approve_btn)

                reject_btn = QPushButton("Отклонить")
                reject_btn.clicked.connect(
                    lambda checked, lot_id=lot.id: self.reject_lot(lot_id)
                )
                reject_btn.setStyleSheet("background-color: #e74c3c; color: white;")
                actions_layout.addWidget(reject_btn)

                view_btn = QPushButton("Просмотр")
                view_btn.clicked.connect(
                    lambda checked, lot_id=lot.id: self.view_lot(lot_id)
                )
                actions_layout.addWidget(view_btn)

                self.pending_lots_table.setCellWidget(row, 7, actions_widget)

        except Exception as e:
            logger.error(f"Ошибка при обновлении лотов на модерации: {e}")
        finally:
            db.close()

    def refresh_complaints(self):
        """Обновляет таблицу жалоб"""
        db = SessionLocal()
        try:
            complaints = db.query(Complaint).order_by(Complaint.created_at.desc()).all()

            self.complaints_table.setRowCount(len(complaints))

            for row, complaint in enumerate(complaints):
                # ID
                self.complaints_table.setItem(
                    row, 0, QTableWidgetItem(str(complaint.id))
                )

                # Жалобщик
                complainant = (
                    db.query(User).filter(User.id == complaint.complainant_id).first()
                )
                if complainant and complainant.username:
                    complainant_name = f"@{complainant.username}"
                elif complainant and complainant.first_name:
                    complainant_name = complainant.first_name
                else:
                    complainant_name = "Неизвестно"
                self.complaints_table.setItem(
                    row, 1, QTableWidgetItem(complainant_name)
                )

                # Тип жалобы
                self.complaints_table.setItem(
                    row,
                    2,
                    QTableWidgetItem(
                        complaint.reason[:30] + "..."
                        if len(complaint.reason) > 30
                        else complaint.reason
                    ),
                )

                # Описание (обрезаем)
                description = (
                    complaint.reason[:50] + "..."
                    if len(complaint.reason) > 50
                    else complaint.reason
                )
                self.complaints_table.setItem(row, 3, QTableWidgetItem(description))

                # Статус
                status = "Решена" if complaint.is_resolved else "На рассмотрении"
                self.complaints_table.setItem(row, 4, QTableWidgetItem(status))

                # Дата
                created_date = format_local_time(complaint.created_at)
                self.complaints_table.setItem(row, 5, QTableWidgetItem(created_date))

                # Действия
                actions_widget = QWidget()
                actions_layout = QHBoxLayout(actions_widget)
                actions_layout.setContentsMargins(0, 0, 0, 0)

                resolve_btn = QPushButton("Решить")
                resolve_btn.clicked.connect(
                    lambda checked, complaint_id=complaint.id: self.resolve_complaint(
                        complaint_id
                    )
                )
                resolve_btn.setStyleSheet("background-color: #3498db; color: white;")
                actions_layout.addWidget(resolve_btn)

                view_btn = QPushButton("Просмотр")
                view_btn.clicked.connect(
                    lambda checked, complaint_id=complaint.id: self.view_complaint(
                        complaint_id
                    )
                )
                actions_layout.addWidget(view_btn)

                self.complaints_table.setCellWidget(row, 6, actions_widget)

        except Exception as e:
            logger.error(f"Ошибка при обновлении жалоб: {e}")
        finally:
            db.close()

    def refresh_statistics(self):
        """Обновляет статистику модерации"""
        db = SessionLocal()
        try:
            # Подсчитываем статистику
            pending_lots = db.query(Lot).filter(Lot.status == LotStatus.PENDING).count()
            approved_lots = db.query(Lot).filter(Lot.status == LotStatus.ACTIVE).count()
            rejected_lots = (
                db.query(Lot).filter(Lot.status == LotStatus.CANCELLED).count()
            )
            pending_complaints = (
                db.query(Complaint).filter(Complaint.is_resolved == False).count()
            )
            resolved_complaints = (
                db.query(Complaint).filter(Complaint.is_resolved == True).count()
            )

            # Обновляем метки
            self.pending_lots_count.setText(str(pending_lots))
            self.approved_lots_count.setText(str(approved_lots))
            self.rejected_lots_count.setText(str(rejected_lots))
            self.pending_complaints_count.setText(str(pending_complaints))
            self.resolved_complaints_count.setText(str(resolved_complaints))

            # Детальная статистика
            total_processed = approved_lots + rejected_lots
            approval_rate = (
                (approved_lots / total_processed * 100) if total_processed > 0 else 0
            )

            stats_text = f"""
Статистика модерации за {datetime.now().strftime('%d.%m.%Y')}:

📦 Лоты:
• На модерации: {pending_lots}
• Одобрено: {approved_lots}
• Отклонено: {rejected_lots}
• Процент одобрения: {approval_rate:.1f}%

📝 Жалобы:
• На рассмотрении: {pending_complaints}
• Решено: {resolved_complaints}
• Всего: {pending_complaints + resolved_complaints}

⏰ Время обработки:
• Среднее время модерации лота: ~5 минут
• Среднее время рассмотрения жалобы: ~2 часа
            """

            self.moderation_stats_text.setText(stats_text.strip())

        except Exception as e:
            logger.error(f"Ошибка при обновлении статистики модерации: {e}")
        finally:
            db.close()

    def refresh_support_questions(self):
        """Обновляет таблицу вопросов поддержки"""
        db = SessionLocal()
        try:
            # Получаем все вопросы поддержки
            questions = (
                db.query(SupportQuestion)
                .order_by(SupportQuestion.created_at.desc())
                .all()
            )

            self.support_questions_table.setRowCount(len(questions))

            for row, question in enumerate(questions):
                # ID
                self.support_questions_table.setItem(
                    row, 0, QTableWidgetItem(str(question.id))
                )

                # Пользователь
                user = db.query(User).filter(User.id == question.user_id).first()
                user_text = (
                    f"@{user.username}"
                    if user and user.username
                    else f"ID: {question.user_id}"
                )
                self.support_questions_table.setItem(
                    row, 1, QTableWidgetItem(user_text)
                )

                # Вопрос (обрезаем до 50 символов)
                question_text = (
                    question.question[:50] + "..."
                    if len(question.question) > 50
                    else question.question
                )
                self.support_questions_table.setItem(
                    row, 2, QTableWidgetItem(question_text)
                )

                # Статус
                status_text = {
                    "pending": "⏳ Ожидает",
                    "answered": "✅ Отвечен",
                    "closed": "🔒 Закрыт",
                }.get(question.status, question.status)
                self.support_questions_table.setItem(
                    row, 3, QTableWidgetItem(status_text)
                )

                # Дата создания
                created_date = format_local_time(question.created_at)
                self.support_questions_table.setItem(
                    row, 4, QTableWidgetItem(created_date)
                )

                # Ответил
                if question.answered_by:
                    moderator = (
                        db.query(User).filter(User.id == question.answered_by).first()
                    )
                    moderator_text = (
                        f"@{moderator.username}"
                        if moderator and moderator.username
                        else f"ID: {question.answered_by}"
                    )
                else:
                    moderator_text = "—"
                self.support_questions_table.setItem(
                    row, 5, QTableWidgetItem(moderator_text)
                )

                # Дата ответа
                if question.answered_at:
                    answered_date = format_local_time(question.answered_at)
                else:
                    answered_date = "—"
                self.support_questions_table.setItem(
                    row, 6, QTableWidgetItem(answered_date)
                )

                # Действия
                actions_widget = QWidget()
                actions_layout = QHBoxLayout(actions_widget)
                actions_layout.setContentsMargins(0, 0, 0, 0)

                if question.status == "pending":
                    answer_btn = QPushButton("Ответить")
                    answer_btn.clicked.connect(
                        lambda checked, q_id=question.id: self.answer_support_question(
                            q_id
                        )
                    )
                    answer_btn.setStyleSheet(
                        """
                        QPushButton {
                            background-color: #3498db;
                            color: white;
                            padding: 4px 8px;
                            border-radius: 3px;
                        }
                        QPushButton:hover {
                            background-color: #2980b9;
                        }
                    """
                    )
                    actions_layout.addWidget(answer_btn)

                view_btn = QPushButton("Просмотр")
                view_btn.clicked.connect(
                    lambda checked, q_id=question.id: self.view_support_question(q_id)
                )
                view_btn.setStyleSheet(
                    """
                    QPushButton {
                        background-color: #95a5a6;
                        color: white;
                        padding: 4px 8px;
                        border-radius: 3px;
                    }
                    QPushButton:hover {
                        background-color: #7f8c8d;
                    }
                """
                )
                actions_layout.addWidget(view_btn)

                self.support_questions_table.setCellWidget(row, 7, actions_widget)

        except Exception as e:
            logger.error(f"Ошибка при обновлении вопросов поддержки: {e}")
            QMessageBox.critical(
                self, "Ошибка", f"Ошибка при обновлении вопросов поддержки: {e}"
            )
        finally:
            db.close()

    def approve_lot(self, lot_id: int):
        """Одобряет лот"""
        db = SessionLocal()
        try:
            lot = db.query(Lot).filter(Lot.id == lot_id).first()
            if lot:
                current_time = datetime.now()

                # Если это немедленный запуск (start_time = None), устанавливаем время
                if lot.start_time is None:
                    # Устанавливаем время старта на текущий момент
                    lot.start_time = current_time
                    # Устанавливаем время окончания через 24 часа
                    lot.end_time = current_time + timedelta(hours=24)

                # Всегда активируем лот при одобрении
                lot.status = LotStatus.ACTIVE
                lot.approved_by = self.main_window.get_current_user()["name"]
                lot.approved_at = datetime.utcnow()
                db.commit()

                # Проверяем, нужно ли публиковать сейчас или планировать на будущее
                if lot.start_time <= current_time:
                    # Время старта уже наступило или немедленный запуск - публикуем сразу
                    from management.core.telegram_publisher_sync import (
                        telegram_publisher_sync,
                    )

                    telegram_publisher_sync.publish_lot(lot_id)

                    QMessageBox.information(
                        self,
                        "Успех",
                        f"Лот {lot_id} одобрен и опубликован в канал!\n"
                        f"Время старта: {format_local_time(lot.start_time)}\n"
                        f"Время окончания: {format_local_time(lot.end_time)}",
                    )
                else:
                    # Время старта в будущем - планируем публикацию
                    from management.core.lot_scheduler import lot_scheduler

                    lot_scheduler.schedule_lot_publication(lot.id, lot.start_time)

                    QMessageBox.information(
                        self,
                        "Успех",
                        f"Лот {lot_id} одобрен и будет опубликован в назначенное время!\n"
                        f"Время старта: {format_local_time(lot.start_time)}\n"
                        f"Время окончания: {format_local_time(lot.end_time)}\n\n"
                        f"Лот будет автоматически опубликован в канал в {format_local_time(lot.start_time)}",
                    )

                self.refresh_pending_lots()

                # Обновляем статистику системы
                if hasattr(self.main_window, "refresh_system_stats"):
                    self.main_window.refresh_system_stats()
        except Exception as e:
            logger.error(f"Ошибка при одобрении лота: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка при одобрении лота: {e}")
        finally:
            db.close()

    def reject_lot(self, lot_id: int):
        """Отклоняет лот"""
        reason, ok = QInputDialog.getText(
            self, "Отклонение лота", "Укажите причину отклонения:"
        )
        if ok and reason:
            db = SessionLocal()
            try:
                lot = db.query(Lot).filter(Lot.id == lot_id).first()
                if lot:
                    lot.status = LotStatus.CANCELLED
                    lot.rejection_reason = reason
                    db.commit()

                    self.refresh_pending_lots()

                    # Обновляем статистику системы
                    if hasattr(self.main_window, "refresh_system_stats"):
                        self.main_window.refresh_system_stats()

                    QMessageBox.information(self, "Успех", f"Лот {lot_id} отклонен")
            except Exception as e:
                logger.error(f"Ошибка при отклонении лота: {e}")
                QMessageBox.critical(self, "Ошибка", f"Ошибка при отклонении лота: {e}")
            finally:
                db.close()

    def view_lot(self, lot_id: int):
        """Просматривает лот"""
        db = SessionLocal()
        try:
            lot = db.query(Lot).filter(Lot.id == lot_id).first()
            if lot:
                # Создаем диалог для просмотра деталей лота
                lot_detail_dialog = LotDetailDialog(lot, self)
                lot_detail_dialog.exec_()
        except Exception as e:
            logger.error(f"Ошибка при просмотре лота: {e}")
        finally:
            db.close()

    def resolve_complaint(self, complaint_id: int):
        """Решает жалобу"""
        db = SessionLocal()
        try:
            complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
            if complaint:
                complaint.is_resolved = True
                db.commit()

                self.refresh_complaints()
                QMessageBox.information(self, "Успех", f"Жалоба {complaint_id} решена")
        except Exception as e:
            logger.error(f"Ошибка при решении жалобы: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка при решении жалобы: {e}")
        finally:
            db.close()

    def answer_support_question(self, question_id: int):
        """Отвечает на вопрос поддержки"""
        answer, ok = QInputDialog.getMultiLineText(
            self, "Ответ на вопрос", "Введите ответ на вопрос пользователя:"
        )
        if ok and answer:
            db = SessionLocal()
            try:
                question = (
                    db.query(SupportQuestion)
                    .filter(SupportQuestion.id == question_id)
                    .first()
                )
                if question:
                    current_user = self.main_window.get_current_user()

                    question.answer = answer
                    question.status = "answered"
                    question.answered_by = current_user["id"]
                    question.answered_at = datetime.now()
                    db.commit()

                    # Примечание: уведомление пользователю будет отправлено через бота
                    # при следующем взаимодействии с ботом

                    self.refresh_support_questions()
                    QMessageBox.information(
                        self, "Успех", f"Ответ на вопрос {question_id} отправлен"
                    )
            except Exception as e:
                logger.error(f"Ошибка при ответе на вопрос: {e}")
                QMessageBox.critical(
                    self, "Ошибка", f"Ошибка при ответе на вопрос: {e}"
                )
            finally:
                db.close()

    def view_support_question(self, question_id: int):
        """Просматривает вопрос поддержки"""
        db = SessionLocal()
        try:
            question = (
                db.query(SupportQuestion)
                .filter(SupportQuestion.id == question_id)
                .first()
            )
            if question:
                user = db.query(User).filter(User.id == question.user_id).first()
                user_name = (
                    f"@{user.username}"
                    if user and user.username
                    else f"ID: {question.user_id}"
                )

                moderator = None
                if question.answered_by:
                    moderator = (
                        db.query(User).filter(User.id == question.answered_by).first()
                    )
                moderator_name = (
                    f"@{moderator.username}"
                    if moderator and moderator.username
                    else "Неизвестно"
                )

                details = f"""
📞 **Детали вопроса поддержки #{question_id}**

👤 **Пользователь:** {user_name}
📅 **Дата создания:** {format_local_time(question.created_at)}
📊 **Статус:** {question.status}

❓ **Вопрос:**
{question.question}

"""

                if question.answer:
                    details += f"""
✅ **Ответ:**
{question.answer}

👨‍💼 **Ответил:** {moderator_name}
📅 **Дата ответа:** {format_local_time(question.answered_at)}
"""
                else:
                    details += "\n⏳ **Ожидает ответа**"

                QMessageBox.information(self, f"Вопрос #{question_id}", details)
        except Exception as e:
            logger.error(f"Ошибка при просмотре вопроса: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка при просмотре вопроса: {e}")
        finally:
            db.close()

    def view_complaint(self, complaint_id: int):
        """Просматривает жалобу"""
        db = SessionLocal()
        try:
            complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
            if complaint:
                complainant = (
                    db.query(User).filter(User.id == complaint.complainant_id).first()
                )
                if complainant and complainant.username:
                    complainant_name = f"@{complainant.username}"
                elif complainant and complainant.first_name:
                    complainant_name = complainant.first_name
                else:
                    complainant_name = "Неизвестно"

                details = f"""
Детали жалобы {complaint_id}:

👤 Жалобщик: {complainant_name}
📝 Причина: {complaint.reason}
{f'📄 Доказательства: {complaint.evidence}' if complaint.evidence else '📄 Доказательства: Не предоставлены'}
📅 Дата: {format_local_time(complaint.created_at)}
✅ Статус: {'Решена' if complaint.is_resolved else 'На рассмотрении'}
                """

                QMessageBox.information(self, f"Жалоба {complaint_id}", details.strip())
        except Exception as e:
            logger.error(f"Ошибка при просмотре жалобы: {e}")
        finally:
            db.close()

    def approve_all_lots(self):
        """Одобряет все лоты на модерации"""
        reply = QMessageBox.question(
            self,
            "Массовое одобрение",
            "Вы уверены, что хотите одобрить все лоты на модерации?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            db = SessionLocal()
            try:
                pending_lots = (
                    db.query(Lot).filter(Lot.status == LotStatus.PENDING).all()
                )
                approved_count = 0
                current_time = datetime.now()

                for lot in pending_lots:
                    # Если это немедленный запуск (start_time = None), устанавливаем время
                    if lot.start_time is None:
                        lot.start_time = current_time
                        lot.end_time = current_time + timedelta(hours=24)

                    lot.status = LotStatus.ACTIVE
                    lot.approved_by = self.main_window.get_current_user()["name"]
                    lot.approved_at = datetime.utcnow()
                    approved_count += 1

                db.commit()

                # Планируем публикацию для лотов с будущим временем старта
                for lot in pending_lots:
                    if lot.start_time is None:
                        # Немедленный запуск - публикуем сразу
                        from management.core.telegram_publisher_sync import (
                            telegram_publisher_sync,
                        )

                        telegram_publisher_sync.publish_lot(lot.id)
                    elif lot.start_time > current_time:
                        # Будущее время старта - планируем публикацию
                        from management.core.lot_scheduler import lot_scheduler

                        lot_scheduler.schedule_lot_publication(lot.id, lot.start_time)
                    else:
                        # Прошлое время старта - публикуем сразу
                        from management.core.telegram_publisher_sync import (
                            telegram_publisher_sync,
                        )

                        telegram_publisher_sync.publish_lot(lot.id)

                self.refresh_pending_lots()
                QMessageBox.information(
                    self, "Успех", f"Одобрено {approved_count} лотов"
                )

            except Exception as e:
                logger.error(f"Ошибка при массовом одобрении: {e}")
                QMessageBox.critical(
                    self, "Ошибка", f"Ошибка при массовом одобрении: {e}"
                )
            finally:
                db.close()
