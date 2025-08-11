import json
import logging
from datetime import datetime, timedelta
from functools import partial

from PyQt5.QtCore import QDateTime, Qt, QTimer
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.orm import joinedload

from bot.utils.finance_manager import finance_manager
from database.db import SessionLocal
from database.models import AutoBid, Bid, DocumentType, Lot, LotStatus, User
from management.utils.document_utils import (
    DocumentGenerator,
    ImageManager,
    LotValidator,
    format_local_time,
)

logger = logging.getLogger(__name__)


class LotDetailDialog(QDialog):
    """Диалог для просмотра деталей лота"""

    def __init__(self, lot: Lot, parent=None):
        super().__init__(parent)
        self.lot = lot
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(f"📦 Детали лота: {self.lot.title}")
        self.setMinimumSize(700, 600)

        layout = QVBoxLayout()

        # Создаем скроллируемую область
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()

        # Информация о лоте
        info_group = QGroupBox("📋 Информация о лоте")
        info_layout = QFormLayout()

        info_layout.addRow("ID:", QLabel(str(self.lot.id)))
        info_layout.addRow("Название:", QLabel(self.lot.title))

        # Описание в отдельном виджете для лучшего отображения
        description_label = QLabel(self.lot.description)
        description_label.setWordWrap(True)
        description_label.setStyleSheet(
            "QLabel { padding: 10px; background-color: #f8f9fa; border-radius: 5px; }"
        )
        info_layout.addRow("Описание:", description_label)

        info_layout.addRow(
            "Стартовая цена:", QLabel(f"{self.lot.starting_price:,.2f} ₽")
        )
        info_layout.addRow("Текущая цена:", QLabel(f"{self.lot.current_price:,.2f} ₽"))

        status_text = {
            LotStatus.DRAFT: "Черновик",
            LotStatus.PENDING: "На модерации",
            LotStatus.ACTIVE: "Активен",
            LotStatus.SOLD: "Продан",
            LotStatus.CANCELLED: "Отменен",
            LotStatus.EXPIRED: "Истек",
        }.get(self.lot.status, "Неизвестно")

        status_label = QLabel(status_text)
        if self.lot.status == LotStatus.PENDING:
            status_label.setStyleSheet(
                "QLabel { color: #856404; background-color: #fff3cd; padding: 5px; border-radius: 3px; }"
            )
        elif self.lot.status == LotStatus.ACTIVE:
            status_label.setStyleSheet(
                "QLabel { color: #155724; background-color: #d4edda; padding: 5px; border-radius: 3px; }"
            )
        elif self.lot.status == LotStatus.SOLD:
            status_label.setStyleSheet(
                "QLabel { color: #721c24; background-color: #f8d7da; padding: 5px; border-radius: 3px; }"
            )

        info_layout.addRow("Статус:", status_label)
        info_layout.addRow(
            "Время старта:", QLabel(format_local_time(self.lot.start_time))
        )
        info_layout.addRow(
            "Время окончания:", QLabel(format_local_time(self.lot.end_time))
        )
        info_layout.addRow("Создан:", QLabel(format_local_time(self.lot.created_at)))

        if self.lot.location:
            info_layout.addRow("Геолокация:", QLabel(self.lot.location))
        if self.lot.seller_link:
            info_layout.addRow("Ссылка продавца:", QLabel(self.lot.seller_link))

        info_group.setLayout(info_layout)
        scroll_layout.addWidget(info_group)

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
                                "QLabel { border: 1px solid #ddd; border-radius: 5px; padding: 5px; }"
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
        if self.lot.bids:
            bids_group = QGroupBox("💰 Статистика ставок")
            bids_layout = QFormLayout()

            total_bids = len(self.lot.bids)
            max_bid = max([bid.amount for bid in self.lot.bids]) if self.lot.bids else 0
            unique_bidders = len(set([bid.bidder_id for bid in self.lot.bids]))

            bids_layout.addRow("Всего ставок:", QLabel(str(total_bids)))
            bids_layout.addRow("Максимальная ставка:", QLabel(f"{max_bid:,.2f} ₽"))
            bids_layout.addRow("Уникальных участников:", QLabel(str(unique_bidders)))

            # Показываем последние ставки
            recent_bids = sorted(
                self.lot.bids, key=lambda x: x.created_at, reverse=True
            )[:5]
            if recent_bids:
                bids_layout.addRow("", QLabel(""))  # Пустая строка
                bids_layout.addRow("Последние ставки:", QLabel(""))
                for i, bid in enumerate(recent_bids):
                    bid_text = f"{i+1}. {bid.amount:,.2f} ₽ ({format_local_time(bid.created_at)})"
                    bids_layout.addRow("", QLabel(bid_text))

            bids_group.setLayout(bids_layout)
            scroll_layout.addWidget(bids_group)

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


class EditLotDialog(QDialog):
    """Диалог для редактирования лота"""

    def __init__(self, lot: Lot, parent=None):
        super().__init__(parent)
        self.lot = lot
        self.new_images = []  # Список новых изображений
        self.new_files = []  # Список новых файлов
        self.init_ui()
        self.load_lot_data()

    def init_ui(self):
        self.setWindowTitle(f"✏️ Редактирование лота: {self.lot.title}")
        self.setMinimumSize(600, 500)

        layout = QVBoxLayout()

        # Форма редактирования
        form_layout = QFormLayout()

        self.title_input = QLineEdit()
        form_layout.addRow("Название:", self.title_input)

        self.description_input = QTextEdit()
        self.description_input.setMaximumHeight(100)
        form_layout.addRow("Описание:", self.description_input)

        self.starting_price_input = QDoubleSpinBox()
        self.starting_price_input.setRange(1, 1000000)
        self.starting_price_input.setSuffix(" ₽")
        form_layout.addRow("Стартовая цена:", self.starting_price_input)

        self.document_type_combo = QComboBox()
        self.document_type_combo.addItems(
            ["Стандартный лот", "Ювелирное изделие", "Историческая ценность"]
        )
        form_layout.addRow("Тип документа:", self.document_type_combo)

        # Время старта
        start_time_group = QGroupBox("⏰ Тип запуска аукциона")
        start_time_layout = QVBoxLayout()

        # Радиокнопки для выбора типа запуска
        self.immediate_start_radio = QRadioButton(
            "🚀 Немедленный запуск (после одобрения)"
        )
        self.immediate_start_radio.setChecked(True)
        self.scheduled_start_radio = QRadioButton("📅 Запланированный запуск")

        start_time_layout.addWidget(self.immediate_start_radio)
        start_time_layout.addWidget(self.scheduled_start_radio)

        # Время старта (видимо только при выборе запланированного запуска)
        self.start_time_input = QDateTimeEdit()
        self.start_time_input.setDateTime(
            QDateTime.currentDateTime().addSecs(3600)
        )  # +1 час
        self.start_time_input.setCalendarPopup(True)
        self.start_time_input.setEnabled(False)  # По умолчанию отключено

        # Подключаем сигналы для управления видимостью
        self.immediate_start_radio.toggled.connect(self.on_start_type_changed)
        self.scheduled_start_radio.toggled.connect(self.on_start_type_changed)

        start_time_layout.addWidget(QLabel("Время старта:"))
        start_time_layout.addWidget(self.start_time_input)

        start_time_group.setLayout(start_time_layout)
        form_layout.addRow("", start_time_group)

        self.location_input = QLineEdit()
        form_layout.addRow("Геолокация:", self.location_input)

        self.seller_link_input = QLineEdit()
        form_layout.addRow("Ссылка продавца:", self.seller_link_input)

        layout.addLayout(form_layout)

        # Секция изображений
        images_group = QGroupBox("🖼️ Изображения")
        images_layout = QVBoxLayout()

        # Текущие изображения
        self.current_images_label = QLabel("Текущие изображения:")
        images_layout.addWidget(self.current_images_label)

        # Кнопки для изображений
        images_buttons_layout = QHBoxLayout()
        add_image_btn = QPushButton("➕ Добавить изображения")
        add_image_btn.clicked.connect(self.add_images)
        images_buttons_layout.addWidget(add_image_btn)

        clear_images_btn = QPushButton("🗑️ Очистить новые")
        clear_images_btn.clicked.connect(self.clear_new_images)
        images_buttons_layout.addWidget(clear_images_btn)

        images_layout.addLayout(images_buttons_layout)

        # Список новых изображений
        self.new_images_label = QLabel("Новые изображения: нет")
        images_layout.addWidget(self.new_images_label)

        images_group.setLayout(images_layout)
        layout.addWidget(images_group)

        # Секция файлов
        files_group = QGroupBox("📄 Файлы")
        files_layout = QVBoxLayout()

        # Текущие файлы
        self.current_files_label = QLabel("Текущие файлы:")
        files_layout.addWidget(self.current_files_label)

        # Кнопки для файлов
        files_buttons_layout = QHBoxLayout()
        add_file_btn = QPushButton("➕ Добавить файлы")
        add_file_btn.clicked.connect(self.add_files)
        files_buttons_layout.addWidget(add_file_btn)

        clear_files_btn = QPushButton("🗑️ Очистить новые")
        clear_files_btn.clicked.connect(self.clear_new_files)
        files_buttons_layout.addWidget(clear_files_btn)

        files_layout.addLayout(files_buttons_layout)

        # Список новых файлов
        self.new_files_label = QLabel("Новые файлы: нет")
        files_layout.addWidget(self.new_files_label)

        files_group.setLayout(files_layout)
        layout.addWidget(files_group)

        # Кнопки
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def load_lot_data(self):
        """Загружает данные лота в форму"""
        self.title_input.setText(self.lot.title)
        self.description_input.setPlainText(self.lot.description)
        self.starting_price_input.setValue(self.lot.starting_price)

        # Устанавливаем тип документа
        doc_type_map = {
            DocumentType.STANDARD: "Стандартный лот",
            DocumentType.JEWELRY: "Ювелирное изделие",
            DocumentType.HISTORICAL: "Историческая ценность",
        }
        index = self.document_type_combo.findText(
            doc_type_map.get(self.lot.document_type, "Стандартный лот")
        )
        if index >= 0:
            self.document_type_combo.setCurrentIndex(index)

        # Настраиваем радио-кнопки и время старта
        if self.lot.start_time is None:
            # Немедленный запуск
            self.immediate_start_radio.setChecked(True)
            self.scheduled_start_radio.setChecked(False)
            self.start_time_input.setEnabled(False)
            self.start_time_input.setDateTime(QDateTime.currentDateTime().addSecs(3600))
        else:
            # Запланированный запуск
            self.immediate_start_radio.setChecked(False)
            self.scheduled_start_radio.setChecked(True)
            self.start_time_input.setEnabled(True)
            self.start_time_input.setDateTime(
                QDateTime.fromString(
                    format_local_time(self.lot.start_time), "dd.MM.yyyy HH:mm"
                )
            )

        if self.lot.location:
            self.location_input.setText(self.lot.location)
        if self.lot.seller_link:
            self.seller_link_input.setText(self.lot.seller_link)

        # Загружаем текущие изображения
        current_images = ImageManager.get_lot_images(self.lot)
        if current_images:
            self.current_images_label.setText(
                f"Текущие изображения: {len(current_images)} файлов"
            )
        else:
            self.current_images_label.setText("Текущие изображения: нет")

        # Загружаем текущие файлы
        current_files = ImageManager.get_lot_files(self.lot)
        if current_files:
            self.current_files_label.setText(
                f"Текущие файлы: {len(current_files)} файлов"
            )
        else:
            self.current_files_label.setText("Текущие файлы: нет")

    def add_images(self):
        """Добавление изображений"""
        from PyQt5.QtWidgets import QFileDialog

        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Выберите изображения",
            "",
            "Изображения (*.png *.jpg *.jpeg *.gif *.bmp)",
        )

        if file_paths:
            self.new_images.extend(file_paths)
            self.update_new_images_label()

    def clear_new_images(self):
        """Очистка новых изображений"""
        self.new_images.clear()
        self.update_new_images_label()

    def update_new_images_label(self):
        """Обновление метки новых изображений"""
        if self.new_images:
            self.new_images_label.setText(
                f"Новые изображения: {len(self.new_images)} файлов"
            )
        else:
            self.new_images_label.setText("Новые изображения: нет")

    def add_files(self):
        """Добавление файлов"""
        from PyQt5.QtWidgets import QFileDialog

        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Выберите файлы", "", "Все файлы (*.*)"
        )

        if file_paths:
            self.new_files.extend(file_paths)
            self.update_new_files_label()

    def clear_new_files(self):
        """Очистка новых файлов"""
        self.new_files.clear()
        self.update_new_files_label()

    def update_new_files_label(self):
        """Обновление метки новых файлов"""
        if self.new_files:
            self.new_files_label.setText(f"Новые файлы: {len(self.new_files)} файлов")
        else:
            self.new_files_label.setText("Новые файлы: нет")

    def on_start_type_changed(self):
        """Обрабатывает изменение типа запуска аукциона"""
        if self.scheduled_start_radio.isChecked():
            self.start_time_input.setEnabled(True)
        else:
            self.start_time_input.setEnabled(False)

    def get_updated_data(self):
        """Возвращает обновленные данные лота"""
        doc_type_map = {
            "Стандартный лот": DocumentType.STANDARD,
            "Ювелирное изделие": DocumentType.JEWELRY,
            "Историческая ценность": DocumentType.HISTORICAL,
        }

        start_time = (
            None
            if self.immediate_start_radio.isChecked()
            else self.start_time_input.dateTime().toPyDateTime()
        )

        # Конвертируем локальное (МСК) время в UTC корректно
        if start_time is not None:
            try:
                from bot.utils.time_utils import moscow_to_utc

                if start_time.tzinfo is None:
                    start_time = moscow_to_utc(start_time)
            except Exception:
                if start_time.tzinfo is None:
                    from datetime import timezone

                    start_time = start_time.replace(tzinfo=timezone.utc)

        # Валидируем время старта
        start_time_errors = LotValidator.validate_start_time(start_time)
        if start_time_errors:
            error_message = "\n".join(start_time_errors)
            QMessageBox.warning(self, "Ошибка валидации", error_message)
            return None

        return {
            "title": self.title_input.text().strip(),
            "description": self.description_input.toPlainText().strip(),
            "starting_price": self.starting_price_input.value(),
            "document_type": doc_type_map.get(
                self.document_type_combo.currentText(), DocumentType.STANDARD
            ),
            "start_time": start_time,
            "location": self.location_input.text().strip(),
            "seller_link": self.seller_link_input.text().strip(),
            "new_images": self.new_images,
            "new_files": self.new_files,
        }


class SellerPanel(QWidget):
    """Панель продавца для создания заявок на лоты"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.current_user = None  # Инициализируем как None
        # Буферы выбора при создании лота
        self.selected_images = []
        self.selected_files = []
        self.init_ui()
        self.setup_timer()

    def init_ui(self):
        """Инициализация интерфейса"""
        self.setWindowTitle("👤 Панель продавца - Не авторизован")
        self.setMinimumSize(1200, 800)

        # Главный layout
        layout = QVBoxLayout()

        # Заголовок с информацией о пользователе
        header = self.create_header()
        layout.addWidget(header)

        # Вкладки
        self.tabs = QTabWidget()
        self.tabs.addTab(self.create_lot_creation_tab(), "📝 Создать лот")
        self.tabs.addTab(self.create_my_lots_tab(), "📦 Мои лоты")
        self.tabs.addTab(self.create_profile_tab(), "👤 Профиль")

        # Подключаем сигнал переключения вкладок
        self.tabs.currentChanged.connect(self.on_tab_changed)

        layout.addWidget(self.tabs)
        self.setLayout(layout)

        # Настраиваем таймер
        self.setup_timer()

    def create_header(self):
        """Создает заголовок панели"""
        header_frame = QFrame()
        header_frame.setFrameStyle(QFrame.StyledPanel)
        header_frame.setStyleSheet(
            "QFrame { background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 5px; }"
        )

        layout = QHBoxLayout()

        # Информация о пользователе
        if self.current_user:
            user_name = self.current_user["name"]
        else:
            user_name = "Не авторизован"

        user_info = QLabel(f"👤 {user_name}")
        user_info.setFont(QFont("Segoe UI", 16, QFont.Bold))
        layout.addWidget(user_info)

        layout.addStretch()

        # Время
        self.time_label = QLabel()
        self.time_label.setFont(QFont("Segoe UI", 12))
        # Инициализируем время сразу
        current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        self.time_label.setText(f"🕐 {current_time}")
        layout.addWidget(self.time_label)

        header_frame.setLayout(layout)
        return header_frame

    def create_lot_creation_tab(self):
        """Создает вкладку создания лота"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Форма создания лота
        form_group = QGroupBox("📝 Информация о лоте")
        form_layout = QFormLayout()

        # Название лота
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Введите название лота")
        form_layout.addRow("Название:", self.title_input)

        # Описание
        self.description_input = QTextEdit()
        self.description_input.setPlaceholderText("Подробное описание лота...")
        self.description_input.setMaximumHeight(100)
        form_layout.addRow("Описание:", self.description_input)

        # Стартовая цена
        self.starting_price_input = QDoubleSpinBox()
        self.starting_price_input.setRange(1, 1000000)
        self.starting_price_input.setSuffix(" ₽")
        self.starting_price_input.setValue(1000)
        form_layout.addRow("Стартовая цена:", self.starting_price_input)

        # Тип документа
        self.document_type_combo = QComboBox()
        self.document_type_combo.addItems(
            ["Стандартный лот", "Ювелирное изделие", "Историческая ценность"]
        )
        form_layout.addRow("Тип документа:", self.document_type_combo)

        # Время старта
        start_time_group = QGroupBox("⏰ Тип запуска аукциона")
        start_time_layout = QVBoxLayout()

        # Радиокнопки для выбора типа запуска
        self.immediate_start_radio = QRadioButton(
            "🚀 Немедленный запуск (после одобрения)"
        )
        self.immediate_start_radio.setChecked(True)
        self.scheduled_start_radio = QRadioButton("📅 Запланированный запуск")

        start_time_layout.addWidget(self.immediate_start_radio)
        start_time_layout.addWidget(self.scheduled_start_radio)

        # Время старта (видимо только при выборе запланированного запуска)
        self.start_time_input = QDateTimeEdit()
        self.start_time_input.setDateTime(
            QDateTime.currentDateTime().addSecs(3600)
        )  # +1 час
        self.start_time_input.setCalendarPopup(True)
        self.start_time_input.setEnabled(False)  # По умолчанию отключено

        # Подключаем сигналы для управления видимостью
        self.immediate_start_radio.toggled.connect(self.on_start_type_changed)
        self.scheduled_start_radio.toggled.connect(self.on_start_type_changed)

        start_time_layout.addWidget(QLabel("Время старта:"))
        start_time_layout.addWidget(self.start_time_input)

        start_time_group.setLayout(start_time_layout)
        form_layout.addRow("", start_time_group)

        # Примечание о времени окончания
        end_time_note = QLabel(
            "⏰ Время окончания аукциона будет автоматически установлено через 24 часа после старта"
        )
        end_time_note.setStyleSheet("QLabel { color: #6c757d; font-style: italic; }")
        form_layout.addRow("", end_time_note)

        # Геолокация
        self.location_input = QLineEdit()
        self.location_input.setPlaceholderText("Адрес или координаты")
        form_layout.addRow("Геолокация:", self.location_input)

        # Ссылка на продавца
        self.seller_link_input = QLineEdit()
        self.seller_link_input.setPlaceholderText("Ссылка на продавца (необязательно)")
        form_layout.addRow("Ссылка продавца:", self.seller_link_input)

        # Загрузка изображений
        images_layout = QHBoxLayout()
        self.images_label = QLabel("Изображения: не выбрано")
        images_layout.addWidget(self.images_label)

        add_images_btn = QPushButton("📷 Добавить изображения")
        add_images_btn.clicked.connect(self.add_images)
        images_layout.addWidget(add_images_btn)

        clear_images_btn = QPushButton("🗑️ Очистить")
        clear_images_btn.clicked.connect(self.clear_images)
        images_layout.addWidget(clear_images_btn)

        form_layout.addRow("Изображения:", images_layout)

        # Секция файлов (произвольные вложения)
        files_layout = QHBoxLayout()
        self.files_label = QLabel("Файлы: не выбрано")
        files_layout.addWidget(self.files_label)

        add_files_btn = QPushButton("📎 Добавить файлы")
        add_files_btn.clicked.connect(self.add_files)
        files_layout.addWidget(add_files_btn)

        clear_files_btn = QPushButton("🗑️ Очистить")
        clear_files_btn.clicked.connect(self.clear_files)
        files_layout.addWidget(clear_files_btn)

        form_layout.addRow("Файлы:", files_layout)

        # Список выбранных изображений
        self.selected_images = []

        form_group.setLayout(form_layout)
        layout.addWidget(form_group)

        # Кнопки
        buttons_layout = QHBoxLayout()

        create_draft_btn = QPushButton("💾 Сохранить черновик")
        create_draft_btn.setStyleSheet("background-color: #6c757d;")
        create_draft_btn.clicked.connect(self.save_draft)
        buttons_layout.addWidget(create_draft_btn)

        submit_btn = QPushButton("📤 Отправить на модерацию")
        submit_btn.setStyleSheet("background-color: #28a745;")
        submit_btn.clicked.connect(self.submit_for_moderation)
        buttons_layout.addWidget(submit_btn)

        layout.addLayout(buttons_layout)
        layout.addStretch()

        widget.setLayout(layout)
        return widget

    def create_my_lots_tab(self):
        """Создает вкладку с лотами продавца"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Фильтры и сортировка
        filters_layout = QHBoxLayout()

        self.lots_status_filter = QComboBox()
        self.lots_status_filter.addItems(
            [
                "Все статусы",
                "Черновик",
                "На модерации",
                "Активен",
                "Продан",
                "Отменен",
                "Истек",
            ]
        )
        filters_layout.addWidget(QLabel("Статус:"))
        filters_layout.addWidget(self.lots_status_filter)

        self.lots_sort_combo = QComboBox()
        self.lots_sort_combo.addItems(
            [
                "По дате (новые)",
                "По дате (старые)",
                "По цене (дороже)",
                "По цене (дешевле)",
                "По статусу",
            ]
        )
        filters_layout.addWidget(QLabel("Сортировка:"))
        filters_layout.addWidget(self.lots_sort_combo)

        self.lots_search_input = QLineEdit()
        self.lots_search_input.setPlaceholderText("Поиск по названию")
        filters_layout.addWidget(self.lots_search_input)

        apply_lot_filters_btn = QPushButton("Применить")
        apply_lot_filters_btn.clicked.connect(self.refresh_my_lots)
        filters_layout.addWidget(apply_lot_filters_btn)

        reset_lot_filters_btn = QPushButton("Сбросить")
        reset_lot_filters_btn.clicked.connect(self.reset_lot_filters)
        filters_layout.addWidget(reset_lot_filters_btn)

        layout.addLayout(filters_layout)

        # Таблица лотов
        self.lots_table = QTableWidget()
        self.lots_table.setColumnCount(9)
        self.lots_table.setHorizontalHeaderLabels(
            [
                "ID",
                "Название",
                "Статус",
                "Цена",
                "Создан",
                "Время старта",
                "Время окончания",
                "Действия",
                "",
            ]
        )
        self.lots_table.horizontalHeader().setStretchLastSection(True)
        self.lots_table.setColumnWidth(0, 50)  # ID
        self.lots_table.setColumnWidth(1, 200)  # Название
        self.lots_table.setColumnWidth(2, 100)  # Статус
        self.lots_table.setColumnWidth(3, 100)  # Цена
        self.lots_table.setColumnWidth(4, 120)  # Создан
        self.lots_table.setColumnWidth(5, 120)  # Время старта
        self.lots_table.setColumnWidth(6, 120)  # Время окончания
        self.lots_table.setColumnWidth(7, 200)  # Действия

        # Включаем контекстное меню
        self.lots_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lots_table.customContextMenuRequested.connect(self.show_context_menu)

        layout.addWidget(self.lots_table)

        # Кнопки
        buttons_layout = QHBoxLayout()

        refresh_btn = QPushButton("🔄 Обновить")
        refresh_btn.clicked.connect(self.refresh_my_lots)
        buttons_layout.addWidget(refresh_btn)

        buttons_layout.addStretch()

        layout.addLayout(buttons_layout)

        widget.setLayout(layout)
        return widget

    def create_profile_tab(self):
        """Создает вкладку профиля"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Информация о профиле
        profile_group = QGroupBox("👤 Информация о профиле")
        profile_layout = QFormLayout()

        # Создаем метки для динамического обновления
        self.name_label = QLabel("Не авторизован")
        self.username_label = QLabel("Не указан")
        self.role_label = QLabel("Не указана")

        profile_layout.addRow("Имя:", self.name_label)
        profile_layout.addRow("Telegram Username:", self.username_label)
        profile_layout.addRow("Роль:", self.role_label)

        profile_group.setLayout(profile_layout)
        layout.addWidget(profile_group)

        # Статистика
        stats_group = QGroupBox("📊 Статистика")
        stats_layout = QVBoxLayout()

        self.stats_label = QLabel("Загрузка статистики...")
        stats_layout.addWidget(self.stats_label)

        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        # Финансы продавца
        finance_group = QGroupBox("💳 Баланс продавца")
        finance_layout = QFormLayout()

        self.seller_balance_label = QLabel("0 ₽")
        finance_layout.addRow("Текущий баланс:", self.seller_balance_label)

        buttons_layout = QHBoxLayout()
        top_up_btn = QPushButton("➕ Пополнить")
        withdraw_btn = QPushButton("➖ Вывести")
        top_up_btn.clicked.connect(self.top_up_seller_balance)
        withdraw_btn.clicked.connect(self.withdraw_seller_balance)
        buttons_layout.addWidget(top_up_btn)
        buttons_layout.addWidget(withdraw_btn)
        finance_layout.addRow(buttons_layout)

        finance_group.setLayout(finance_layout)
        layout.addWidget(finance_group)

        layout.addStretch()

        widget.setLayout(layout)
        return widget

    def setup_timer(self):
        """Настраивает таймер для обновления времени"""
        try:
            self.timer = QTimer()
            self.timer.timeout.connect(self.update_time)
            self.timer.start(1000)  # Обновление каждую секунду
            logger.info("Таймер времени успешно запущен")
        except Exception as e:
            logger.error(f"Ошибка при настройке таймера: {e}")

    def update_time(self):
        """Обновляет время"""
        try:
            if hasattr(self, "time_label") and self.time_label:
                # Используем локальное время с правильным форматированием
                current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                self.time_label.setText(f"🕐 {current_time}")
                # Принудительно обновляем виджет
                self.time_label.repaint()
        except Exception as e:
            logger.error(f"Ошибка при обновлении времени: {e}")

    def on_start_type_changed(self):
        """Обрабатывает изменение типа запуска аукциона"""
        if self.scheduled_start_radio.isChecked():
            self.start_time_input.setEnabled(True)
        else:
            self.start_time_input.setEnabled(False)

    def save_draft(self):
        """Сохраняет черновик лота"""
        if not self.current_user:
            QMessageBox.warning(self, "Ошибка", "Необходимо авторизоваться")
            return

        try:
            # Получаем данные из формы
            title = self.title_input.text().strip()
            description = self.description_input.toPlainText().strip()
            starting_price = self.starting_price_input.value()

            # Определяем время старта в зависимости от выбора пользователя
            if self.immediate_start_radio.isChecked():
                start_time = None  # Немедленный запуск после одобрения
            else:
                start_time = self.start_time_input.dateTime().toPyDateTime()

            # Валидируем данные
            lot_data = {
                "title": title,
                "description": description,
                "starting_price": starting_price,
                "start_time": start_time,
            }

            errors = LotValidator.validate_lot_data(lot_data)

            # Добавляем валидацию времени старта
            start_time_errors = LotValidator.validate_start_time(start_time)
            errors.extend(start_time_errors)

            if errors:
                error_message = "\n".join(errors)
                QMessageBox.warning(self, "Ошибка валидации", error_message)
                return

            # Определяем тип документа
            doc_type_map = {
                "Стандартный лот": DocumentType.STANDARD,
                "Ювелирное изделие": DocumentType.JEWELRY,
                "Историческая ценность": DocumentType.HISTORICAL,
            }
            document_type = doc_type_map.get(
                self.document_type_combo.currentText(), DocumentType.STANDARD
            )

            # Создаем лот в статусе черновика
            db = SessionLocal()
            try:
                new_lot = Lot(
                    title=title,
                    description=description,
                    starting_price=starting_price,
                    current_price=starting_price,
                    min_bid_increment=1.0,
                    seller_id=self.current_user["id"],
                    status=LotStatus.DRAFT,
                    document_type=document_type,
                    start_time=start_time,
                    end_time=start_time + timedelta(hours=24) if start_time else None,
                    location=self.location_input.text().strip(),
                    seller_link=self.seller_link_input.text().strip(),
                )

                db.add(new_lot)
                db.commit()

                # Сохраняем изображения
                if self.selected_images:
                    saved_paths = ImageManager.save_images_for_lot(
                        new_lot.id, self.selected_images
                    )
                    if saved_paths:
                        new_lot.images = json.dumps(saved_paths)
                        db.commit()

                # Сохраняем файлы
                if hasattr(self, "selected_files") and self.selected_files:
                    file_paths = ImageManager.save_files_for_lot(
                        new_lot.id, self.selected_files
                    )
                    if file_paths:
                        new_lot.files = json.dumps(file_paths)
                        db.commit()

                QMessageBox.information(
                    self,
                    "Успех",
                    f"Черновик лота '{title}' сохранен!\nID лота: {new_lot.id}",
                )

                # Очищаем форму
                self.clear_form()
                self.refresh_my_lots()

                # Обновляем статистику системы
                if hasattr(self.main_window, "refresh_system_stats"):
                    self.main_window.refresh_system_stats()

            except Exception as e:
                logger.error(f"Ошибка при сохранении черновика: {e}")
                QMessageBox.critical(self, "Ошибка", f"Ошибка при сохранении: {e}")
            finally:
                db.close()

        except Exception as e:
            logger.error(f"Ошибка при сохранении черновика: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка при сохранении: {e}")

    def submit_for_moderation(self):
        """Отправляет лот на модерацию"""
        if not self.current_user:
            QMessageBox.warning(self, "Ошибка", "Необходимо авторизоваться")
            return

        try:
            # Получаем данные из формы
            title = self.title_input.text().strip()
            description = self.description_input.toPlainText().strip()
            starting_price = self.starting_price_input.value()

            # Определяем время старта в зависимости от выбора пользователя
            if self.immediate_start_radio.isChecked():
                start_time = None  # Немедленный запуск после одобрения
            else:
                start_time = self.start_time_input.dateTime().toPyDateTime()
                # Конвертируем МСК -> UTC корректно
                try:
                    from bot.utils.time_utils import moscow_to_utc

                    if start_time.tzinfo is None:
                        start_time = moscow_to_utc(start_time)
                except Exception:
                    if start_time.tzinfo is None:
                        from datetime import timezone

                        start_time = start_time.replace(tzinfo=timezone.utc)

            # Валидируем данные
            lot_data = {
                "title": title,
                "description": description,
                "starting_price": starting_price,
                "start_time": start_time,
            }

            errors = LotValidator.validate_lot_data(lot_data)

            # Добавляем валидацию времени старта
            start_time_errors = LotValidator.validate_start_time(start_time)
            errors.extend(start_time_errors)

            if errors:
                error_message = "\n".join(errors)
                QMessageBox.warning(self, "Ошибка валидации", error_message)
                return

            # Определяем тип документа
            doc_type_map = {
                "Стандартный лот": DocumentType.STANDARD,
                "Ювелирное изделие": DocumentType.JEWELRY,
                "Историческая ценность": DocumentType.HISTORICAL,
            }
            document_type = doc_type_map.get(
                self.document_type_combo.currentText(), DocumentType.STANDARD
            )

            # Создаем лот в статусе на модерации
            db = SessionLocal()
            try:
                new_lot = Lot(
                    title=title,
                    description=description,
                    starting_price=starting_price,
                    current_price=starting_price,
                    min_bid_increment=1.0,
                    seller_id=self.current_user["id"],
                    status=LotStatus.PENDING,
                    document_type=document_type,
                    start_time=start_time,
                    end_time=start_time + timedelta(hours=24) if start_time else None,
                    location=self.location_input.text().strip(),
                    seller_link=self.seller_link_input.text().strip(),
                )

                db.add(new_lot)
                db.commit()

                # Сохраняем изображения
                if self.selected_images:
                    saved_paths = ImageManager.save_images_for_lot(
                        new_lot.id, self.selected_images
                    )
                    if saved_paths:
                        new_lot.images = json.dumps(saved_paths)
                        db.commit()

                # Сохраняем файлы
                if hasattr(self, "selected_files") and self.selected_files:
                    file_paths = ImageManager.save_files_for_lot(
                        new_lot.id, self.selected_files
                    )
                    if file_paths:
                        new_lot.files = json.dumps(file_paths)
                        db.commit()

                QMessageBox.information(
                    self,
                    "Успех",
                    f"Лот '{title}' отправлен на модерацию!\nID лота: {new_lot.id}\n"
                    "Ожидайте одобрения модератором.",
                )

                # Очищаем форму
                self.clear_form()
                self.refresh_my_lots()

                # Обновляем статистику системы
                if hasattr(self.main_window, "refresh_system_stats"):
                    self.main_window.refresh_system_stats()

            except Exception as e:
                logger.error(f"Ошибка при отправке на модерацию: {e}")
                QMessageBox.critical(self, "Ошибка", f"Ошибка при отправке: {e}")
            finally:
                db.close()

        except Exception as e:
            logger.error(f"Ошибка при отправке на модерацию: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка при отправке: {e}")

    def add_images(self):
        """Добавляет изображения к лоту"""
        file_dialog = QFileDialog()
        file_dialog.setNameFilter("Изображения (*.png *.jpg *.jpeg *.gif *.bmp)")
        file_dialog.setFileMode(QFileDialog.ExistingFiles)

        if file_dialog.exec_():
            files = file_dialog.selectedFiles()
            self.selected_images.extend(files)
            self.update_images_label()

    def add_files(self):
        """Добавляет произвольные файлы к лоту"""
        file_dialog = QFileDialog()
        file_dialog.setNameFilter("Все файлы (*.*)")
        file_dialog.setFileMode(QFileDialog.ExistingFiles)

        if file_dialog.exec_():
            files = file_dialog.selectedFiles()
            self.selected_files.extend(files)
            self.update_files_label()

    def clear_images(self):
        """Очищает список изображений"""
        self.selected_images.clear()
        self.update_images_label()

    def clear_files(self):
        """Очищает список файлов"""
        self.selected_files.clear()
        self.update_files_label()

    def update_images_label(self):
        """Обновляет метку с количеством изображений"""
        if self.selected_images:
            self.images_label.setText(
                f"Изображения: {len(self.selected_images)} файлов"
            )
        else:
            self.images_label.setText("Изображения: не выбрано")

    def update_files_label(self):
        """Обновляет метку с количеством файлов"""
        if self.selected_files:
            self.files_label.setText(f"Файлы: {len(self.selected_files)} шт.")
        else:
            self.files_label.setText("Файлы: не выбрано")

    def clear_form(self):
        """Очищает форму создания лота"""
        self.title_input.clear()
        self.description_input.clear()
        self.starting_price_input.setValue(1000)
        self.document_type_combo.setCurrentIndex(0)

        # Сбрасываем радиокнопки и время старта
        self.immediate_start_radio.setChecked(True)
        self.scheduled_start_radio.setChecked(False)
        self.start_time_input.setEnabled(False)
        self.start_time_input.setDateTime(QDateTime.currentDateTime().addSecs(3600))

        self.location_input.clear()
        self.seller_link_input.clear()
        self.clear_images()
        self.clear_files()

    def refresh_my_lots(self):
        """Обновляет таблицу лотов продавца"""
        if not self.current_user:
            self.lots_table.setRowCount(0)
            return

        db = SessionLocal()
        try:
            query = db.query(Lot).filter(Lot.seller_id == self.current_user["id"])

            # Фильтр по статусу
            if hasattr(self, "lots_status_filter"):
                status_text = self.lots_status_filter.currentText()
                status_map = {
                    "Черновик": LotStatus.DRAFT,
                    "На модерации": LotStatus.PENDING,
                    "Активен": LotStatus.ACTIVE,
                    "Продан": LotStatus.SOLD,
                    "Отменен": LotStatus.CANCELLED,
                    "Истек": LotStatus.EXPIRED,
                }
                if status_text and status_text != "Все статусы":
                    query = query.filter(Lot.status == status_map[status_text])

            # Поиск по названию
            if hasattr(self, "lots_search_input"):
                term = self.lots_search_input.text().strip()
                if term:
                    like = f"%{term}%"
                    query = query.filter(Lot.title.ilike(like))

            # Сортировка
            if hasattr(self, "lots_sort_combo"):
                sort_text = self.lots_sort_combo.currentText()
                if sort_text == "По дате (старые)":
                    query = query.order_by(Lot.created_at.asc())
                elif sort_text == "По цене (дороже)":
                    query = query.order_by(Lot.current_price.desc())
                elif sort_text == "По цене (дешевле)":
                    query = query.order_by(Lot.current_price.asc())
                elif sort_text == "По статусу":
                    query = query.order_by(Lot.status.asc(), Lot.created_at.desc())
                else:  # По дате (новые)
                    query = query.order_by(Lot.created_at.desc())

            lots = query.all()

            self.lots_table.setRowCount(len(lots))

            for row, lot in enumerate(lots):
                # ID
                self.lots_table.setItem(row, 0, QTableWidgetItem(str(lot.id)))

                # Название
                self.lots_table.setItem(row, 1, QTableWidgetItem(lot.title))

                # Статус
                status_text = {
                    LotStatus.DRAFT: "Черновик",
                    LotStatus.PENDING: "На модерации",
                    LotStatus.ACTIVE: "Активен",
                    LotStatus.SOLD: "Продан",
                    LotStatus.CANCELLED: "Отменен",
                    LotStatus.EXPIRED: "Истек",
                }.get(lot.status, "Неизвестно")

                status_item = QTableWidgetItem(status_text)
                if lot.status == LotStatus.PENDING:
                    status_item.setBackground(Qt.yellow)
                elif lot.status == LotStatus.ACTIVE:
                    status_item.setBackground(Qt.green)
                elif lot.status == LotStatus.SOLD:
                    status_item.setBackground(Qt.blue)

                self.lots_table.setItem(row, 2, status_item)

                # Цена
                self.lots_table.setItem(
                    row, 3, QTableWidgetItem(f"{lot.current_price:,.2f} ₽")
                )

                # Дата создания
                created_date = format_local_time(lot.created_at)
                self.lots_table.setItem(row, 4, QTableWidgetItem(created_date))

                # Время старта
                start_date = format_local_time(lot.start_time)
                self.lots_table.setItem(row, 5, QTableWidgetItem(start_date))

                # Время окончания
                end_date = format_local_time(lot.end_time)
                self.lots_table.setItem(row, 6, QTableWidgetItem(end_date))

                # Создаем кнопки действий
                actions_widget = QWidget()
                actions_layout = QHBoxLayout()
                actions_layout.setContentsMargins(2, 2, 2, 2)

                # Кнопка просмотра
                view_btn = QPushButton("👁️")
                view_btn.setToolTip("Просмотреть детали")
                view_btn.setMaximumSize(30, 25)
                view_btn.clicked.connect(
                    lambda checked, lot_ref=lot: self.view_lot(lot_ref)
                )
                actions_layout.addWidget(view_btn)

                # Кнопки в зависимости от статуса
                if lot.status == LotStatus.DRAFT:
                    # Кнопка редактирования
                    edit_btn = QPushButton("✏️")
                    edit_btn.setToolTip("Редактировать")
                    edit_btn.setMaximumSize(30, 25)
                    edit_btn.clicked.connect(
                        lambda checked, lot_ref=lot: self.edit_lot(lot_ref)
                    )
                    actions_layout.addWidget(edit_btn)

                    # Кнопка удаления
                    delete_btn = QPushButton("🗑️")
                    delete_btn.setToolTip("Удалить")
                    delete_btn.setMaximumSize(30, 25)
                    delete_btn.setStyleSheet("background-color: #dc3545; color: white;")
                    delete_btn.clicked.connect(
                        lambda checked, lot_ref=lot: self.delete_lot(lot_ref)
                    )
                    actions_layout.addWidget(delete_btn)

                    # Кнопка отправки на модерацию
                    submit_btn = QPushButton("📤")
                    submit_btn.setToolTip("Отправить на модерацию")
                    submit_btn.setMaximumSize(30, 25)
                    submit_btn.setStyleSheet("background-color: #28a745; color: white;")
                    submit_btn.clicked.connect(
                        lambda checked, lot_ref=lot: self.submit_lot_for_moderation(
                            lot_ref
                        )
                    )
                    actions_layout.addWidget(submit_btn)

                elif lot.status == LotStatus.PENDING:
                    # Кнопка отмены отправки
                    cancel_btn = QPushButton("❌")
                    cancel_btn.setToolTip("Отменить отправку")
                    cancel_btn.setMaximumSize(30, 25)
                    cancel_btn.setStyleSheet("background-color: #ffc107; color: black;")
                    # Используем functools.partial для правильной передачи параметра
                    cancel_btn.clicked.connect(partial(self.cancel_submission, lot))
                    actions_layout.addWidget(cancel_btn)

                elif lot.status == LotStatus.ACTIVE:
                    # Кнопка удаления лота
                    delete_btn = QPushButton("🗑️")
                    delete_btn.setToolTip("Удалить лот")
                    delete_btn.setMaximumSize(30, 25)
                    delete_btn.setStyleSheet("background-color: #dc3545; color: white;")
                    delete_btn.clicked.connect(
                        lambda checked, lot_ref=lot: self.delete_active_lot(lot_ref)
                    )
                    actions_layout.addWidget(delete_btn)

                actions_layout.addStretch()
                actions_widget.setLayout(actions_layout)
                self.lots_table.setCellWidget(row, 7, actions_widget)

        except Exception as e:
            logger.error(f"Ошибка при обновлении лотов: {e}")
        finally:
            db.close()

    def reset_lot_filters(self):
        """Сбрасывает фильтры лотов"""
        try:
            if hasattr(self, "lots_status_filter"):
                self.lots_status_filter.setCurrentIndex(0)
            if hasattr(self, "lots_sort_combo"):
                self.lots_sort_combo.setCurrentIndex(0)
            if hasattr(self, "lots_search_input"):
                self.lots_search_input.clear()
        except Exception:
            pass
        self.refresh_my_lots()

    def view_lot(self, lot: Lot):
        """Просмотр деталей лота"""
        db = SessionLocal()
        try:
            # Перезагружаем лот с жадной загрузкой ставок
            fetched_lot = (
                db.query(Lot)
                .options(joinedload(Lot.bids))
                .filter(Lot.id == lot.id)
                .first()
            )
            if fetched_lot:
                dialog = LotDetailDialog(fetched_lot, self)
                dialog.exec_()
            else:
                QMessageBox.warning(self, "Ошибка", "Лот не найден.")
        except Exception as e:
            logger.error(f"Ошибка при просмотре лота: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка при просмотре лота: {e}")
        finally:
            db.close()

    def edit_lot(self, lot: Lot):
        """Редактирование лота"""
        if not LotValidator.can_edit_lot(lot):
            QMessageBox.warning(self, "Ошибка", "Можно редактировать только черновики")
            return

        dialog = EditLotDialog(lot, self)
        if dialog.exec_() == QDialog.Accepted:
            try:
                updated_data = dialog.get_updated_data()

                # Проверяем, что валидация прошла успешно
                if updated_data is None:
                    return  # Валидация не прошла, данные не сохраняем

                db = SessionLocal()
                try:
                    # Перезагружаем лот из базы данных
                    db_lot = db.query(Lot).filter(Lot.id == lot.id).first()
                    if not db_lot:
                        QMessageBox.warning(
                            self, "Ошибка", "Лот не найден в базе данных"
                        )
                        return

                    # Обновляем лот
                    db_lot.title = updated_data["title"]
                    db_lot.description = updated_data["description"]
                    db_lot.starting_price = updated_data["starting_price"]
                    db_lot.current_price = updated_data[
                        "starting_price"
                    ]  # Обновляем текущую цену
                    db_lot.document_type = updated_data["document_type"]
                    db_lot.start_time = updated_data["start_time"]
                    # Автоматически рассчитываем время окончания как start_time + 24 часа
                    if updated_data["start_time"] is not None:
                        db_lot.end_time = updated_data["start_time"] + timedelta(
                            hours=24
                        )
                    else:
                        db_lot.end_time = None
                    db_lot.location = updated_data["location"]
                    db_lot.seller_link = updated_data["seller_link"]
                    db_lot.updated_at = datetime.now()

                    # Обрабатываем новые изображения
                    if updated_data.get("new_images"):
                        new_image_paths = ImageManager.save_images_for_lot(
                            db_lot.id, updated_data["new_images"]
                        )
                        if new_image_paths:
                            # Добавляем новые изображения к существующим
                            current_images = ImageManager.get_lot_images(db_lot)
                            all_images = current_images + new_image_paths
                            db_lot.images = json.dumps(all_images)

                    # Обрабатываем новые файлы
                    if updated_data.get("new_files"):
                        new_file_paths = ImageManager.save_files_for_lot(
                            db_lot.id, updated_data["new_files"]
                        )
                        if new_file_paths:
                            # Добавляем новые файлы к существующим
                            current_files = ImageManager.get_lot_files(db_lot)
                            all_files = current_files + new_file_paths
                            db_lot.files = json.dumps(all_files)

                    db.commit()

                    QMessageBox.information(self, "Успех", "Лот успешно обновлен!")
                    self.refresh_my_lots()

                    # Обновляем статистику системы
                    if hasattr(self.main_window, "refresh_system_stats"):
                        self.main_window.refresh_system_stats()

                except Exception as e:
                    logger.error(f"Ошибка при обновлении лота: {e}")
                    QMessageBox.critical(self, "Ошибка", f"Ошибка при обновлении: {e}")
                finally:
                    db.close()

            except Exception as e:
                logger.error(f"Ошибка при редактировании лота: {e}")
                QMessageBox.critical(self, "Ошибка", f"Ошибка при редактировании: {e}")

    def delete_lot(self, lot: Lot):
        """Удаление лота"""
        if not LotValidator.can_delete_lot(lot):
            QMessageBox.warning(self, "Ошибка", "Можно удалять только черновики")
            return

        reply = QMessageBox.question(
            self,
            "Подтверждение удаления",
            f"Вы уверены, что хотите удалить лот '{lot.title}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            try:
                db = SessionLocal()
                try:
                    # Удаляем изображения лота
                    ImageManager.delete_lot_images(lot.id)

                    db.delete(lot)
                    db.commit()

                    QMessageBox.information(self, "Успех", "Лот успешно удален!")
                    self.refresh_my_lots()

                    # Обновляем статистику системы
                    if hasattr(self.main_window, "refresh_system_stats"):
                        self.main_window.refresh_system_stats()

                except Exception as e:
                    logger.error(f"Ошибка при удалении лота: {e}")
                    QMessageBox.critical(self, "Ошибка", f"Ошибка при удалении: {e}")
                finally:
                    db.close()

            except Exception as e:
                logger.error(f"Ошибка при удалении лота: {e}")
                QMessageBox.critical(self, "Ошибка", f"Ошибка при удалении: {e}")

    def submit_lot_for_moderation(self, lot: Lot):
        """Отправка лота на модерацию"""
        try:
            # Проверяем, что лот существует
            if not lot:
                QMessageBox.warning(self, "Ошибка", "Лот не найден")
                return

            if not LotValidator.can_submit_for_moderation(lot):
                QMessageBox.warning(
                    self, "Ошибка", "Лот не может быть отправлен на модерацию"
                )
                return

            reply = QMessageBox.question(
                self,
                "Подтверждение отправки",
                f"Отправить лот '{lot.title}' на модерацию?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )

            if reply == QMessageBox.Yes:
                db = SessionLocal()
                try:
                    # Перезагружаем лот из базы данных
                    db_lot = db.query(Lot).filter(Lot.id == lot.id).first()
                    if not db_lot:
                        QMessageBox.warning(
                            self, "Ошибка", "Лот не найден в базе данных"
                        )
                        return

                    if not LotValidator.can_submit_for_moderation(db_lot):
                        QMessageBox.warning(
                            self, "Ошибка", "Лот не может быть отправлен на модерацию"
                        )
                        return

                    # Обновляем статус лота
                    db_lot.status = LotStatus.PENDING
                    db_lot.updated_at = datetime.now()
                    db.commit()

                    QMessageBox.information(
                        self,
                        "Успех",
                        f"Лот '{db_lot.title}' отправлен на модерацию!\nОжидайте одобрения модератором.",
                    )
                    self.refresh_my_lots()

                    # Обновляем статистику системы
                    if hasattr(self.main_window, "refresh_system_stats"):
                        self.main_window.refresh_system_stats()

                except Exception as e:
                    logger.error(f"Ошибка при отправке лота: {e}")
                    QMessageBox.critical(self, "Ошибка", f"Ошибка при отправке: {e}")
                finally:
                    db.close()

        except Exception as e:
            logger.error(f"Ошибка при отправке лота: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка при отправке: {e}")

    def cancel_submission(self, lot: Lot):
        """Отмена отправки лота на модерацию"""
        try:
            # Проверяем, что лот существует и имеет правильный статус
            if not lot:
                QMessageBox.warning(self, "Ошибка", "Лот не найден")
                return

            if lot.status != LotStatus.PENDING:
                QMessageBox.warning(
                    self, "Ошибка", "Можно отменять только лоты на модерации"
                )
                return

            reply = QMessageBox.question(
                self,
                "Подтверждение отмены",
                f"Отменить отправку лота '{lot.title}' на модерацию?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )

            if reply == QMessageBox.Yes:
                db = SessionLocal()
                try:
                    # Перезагружаем лот из базы данных
                    db_lot = db.query(Lot).filter(Lot.id == lot.id).first()
                    if not db_lot:
                        QMessageBox.warning(
                            self, "Ошибка", "Лот не найден в базе данных"
                        )
                        return

                    if db_lot.status != LotStatus.PENDING:
                        QMessageBox.warning(
                            self,
                            "Ошибка",
                            "Статус лота изменился. Можно отменять только лоты на модерации",
                        )
                        return

                    # Обновляем статус лота
                    db_lot.status = LotStatus.DRAFT
                    db_lot.updated_at = datetime.now()
                    db.commit()

                    QMessageBox.information(self, "Успех", "Отправка лота отменена!")
                    self.refresh_my_lots()

                except Exception as e:
                    logger.error(f"Ошибка при отмене отправки: {e}")
                    QMessageBox.critical(self, "Ошибка", f"Ошибка при отмене: {e}")
                finally:
                    db.close()

        except Exception as e:
            logger.error(f"Ошибка при отмене отправки: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка при отмене: {e}")

    def stop_auction(self, lot: Lot):
        """Остановка активного аукциона"""
        if lot.status != LotStatus.ACTIVE:
            QMessageBox.warning(
                self, "Ошибка", "Можно останавливать только активные аукционы"
            )
            return

        reply = QMessageBox.question(
            self,
            "Подтверждение остановки",
            f"Остановить аукцион лота '{lot.title}'?\nЭто действие нельзя отменить.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            try:
                db = SessionLocal()
                try:
                    lot.status = LotStatus.CANCELLED
                    lot.updated_at = datetime.now()
                    db.commit()

                    QMessageBox.information(self, "Успех", "Аукцион остановлен!")
                    self.refresh_my_lots()

                except Exception as e:
                    logger.error(f"Ошибка при остановке аукциона: {e}")
                    QMessageBox.critical(self, "Ошибка", f"Ошибка при остановке: {e}")
                finally:
                    db.close()

            except Exception as e:
                logger.error(f"Ошибка при остановке аукциона: {e}")
                QMessageBox.critical(self, "Ошибка", f"Ошибка при остановке: {e}")

    def delete_active_lot(self, lot: Lot):
        """Удаление активного лота с уведомлением в Telegram"""
        reply = QMessageBox.question(
            self,
            "Подтверждение удаления",
            f"Удалить лот '{lot.title}'?\nЭто действие нельзя отменить.\nЛот будет полностью удален из системы.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            try:
                db = SessionLocal()
                try:
                    # Перезагружаем лот в актуальной сессии
                    db_lot = db.query(Lot).filter(Lot.id == lot.id).first()
                    if not db_lot:
                        QMessageBox.warning(self, "Ошибка", "Лот не найден")
                        return

                    if db_lot.status != LotStatus.ACTIVE:
                        QMessageBox.warning(
                            self, "Ошибка", "Можно удалять только активные лоты"
                        )
                        return

                    # Рассчитываем и списываем штраф 5% и зачисляем площадке
                    from bot.utils.finance_manager import finance_manager

                    if not finance_manager.process_lot_deletion(
                        db_lot.id, db_lot.seller_id
                    ):
                        QMessageBox.critical(
                            self, "Ошибка", "Не удалось списать штраф 5% с продавца"
                        )
                        return

                    # Проверяем, есть ли ставки на лот
                    bids_count = db.query(Bid).filter(Bid.lot_id == db_lot.id).count()
                    had_bids = bids_count > 0

                    # Удаляем все ставки на лот
                    db.query(Bid).filter(Bid.lot_id == db_lot.id).delete()

                    # Удаляем все автоставки на лот (во избежание NOT NULL constraints)
                    db.query(AutoBid).filter(AutoBid.lot_id == db_lot.id).delete()

                    # Сохраняем информацию о лоте перед удалением
                    lot_id = db_lot.id
                    lot_title = db_lot.title
                    telegram_message_id = db_lot.telegram_message_id

                    # Удаляем сам лот
                    db.delete(db_lot)
                    db.commit()

                    # Редактируем или отправляем уведомление в Telegram канал
                    try:
                        from management.core.telegram_publisher_sync import (
                            telegram_publisher_sync,
                        )

                        if telegram_message_id:
                            # Редактируем существующее сообщение
                            if had_bids:
                                edit_text = f"""
❌ <b>ЛОТ УДАЛЕН</b>

📦 <b>Лот #{lot_id}: {lot_title}</b>

⚠️ <b>Аукцион завершен досрочно</b>
📊 <b>Были сделаны ставки</b>

💡 <b>Причина:</b> Лот удален продавцом
                                """
                            else:
                                edit_text = f"""
❌ <b>ЛОТ УДАЛЕН</b>

📦 <b>Лот #{lot_id}: {lot_title}</b>

⚠️ <b>Аукцион завершен</b>
📊 <b>Победителей нет</b>

💡 <b>Причина:</b> Лот удален продавцом
                                """

                            telegram_publisher_sync.edit_lot_message(
                                lot_id, telegram_message_id, edit_text.strip()
                            )
                        else:
                            # Отправляем новое сообщение если ID не найден
                            telegram_publisher_sync.send_lot_deleted_message(
                                lot_id, lot_title, had_bids
                            )
                    except Exception as telegram_error:
                        logger.error(
                            f"Ошибка при отправке уведомления в Telegram: {telegram_error}"
                        )

                    QMessageBox.information(
                        self,
                        "Успех",
                        f"Лот '{lot_title}' удален! Штраф 5% списан.\n"
                        f"Ставок на лот: {bids_count}\n"
                        "Уведомление отправлено в Telegram канал.",
                    )
                    self.refresh_my_lots()

                except Exception as e:
                    logger.error(f"Ошибка при удалении лота: {e}")
                    QMessageBox.critical(self, "Ошибка", f"Ошибка при удалении: {e}")
                finally:
                    db.close()

            except Exception as e:
                logger.error(f"Ошибка при удалении лота: {e}")
                QMessageBox.critical(self, "Ошибка", f"Ошибка при удалении: {e}")

    def refresh_data(self):
        """Обновляет все данные"""
        # Обновляем данные пользователя
        self.current_user = self.main_window.get_current_user()

        # Обновляем заголовок
        if hasattr(self, "tabs"):
            # Удаляем старый заголовок
            if self.layout().count() > 0:
                old_header = self.layout().itemAt(0).widget()
                if old_header:
                    old_header.deleteLater()

            # Создаем новый заголовок
            new_header = self.create_header()
            self.layout().insertWidget(0, new_header)

        # Обновляем заголовок окна
        if self.current_user:
            self.setWindowTitle(f"👤 Панель продавца - {self.current_user['name']}")
        else:
            self.setWindowTitle("👤 Панель продавца - Не авторизован")

        self.refresh_my_lots()
        self.update_profile_stats()

        # Принудительно обновляем профиль при каждом обновлении данных
        if hasattr(self, "name_label") and self.current_user:
            self.name_label.setText(self.current_user["name"])
            username = self.current_user.get("username", "Не указан")
            self.username_label.setText(
                f"@{username}" if username != "Не указан" else username
            )
            self.role_label.setText(self.current_user.get("role", "Продавец"))

    def update_profile_stats(self):
        """Обновляет статистику профиля"""
        # Обновляем данные пользователя
        self.current_user = self.main_window.get_current_user()

        if not self.current_user:
            self.stats_label.setText("Не авторизован")
            # Обновляем метки профиля
            if hasattr(self, "name_label"):
                self.name_label.setText("Не авторизован")
                self.username_label.setText("Не указан")
                self.role_label.setText("Не указана")
            return

        # Обновляем метки профиля
        if hasattr(self, "name_label"):
            self.name_label.setText(self.current_user["name"])
            username = self.current_user.get("username", "Не указан")
            self.username_label.setText(
                f"@{username}" if username != "Не указан" else username
            )
            self.role_label.setText(self.current_user.get("role", "Продавец"))

        db = SessionLocal()
        try:
            # Подсчитываем статистику
            total_lots = (
                db.query(Lot).filter(Lot.seller_id == self.current_user["id"]).count()
            )
            active_lots = (
                db.query(Lot)
                .filter(
                    Lot.seller_id == self.current_user["id"],
                    Lot.status == LotStatus.ACTIVE,
                )
                .count()
            )
            sold_lots = (
                db.query(Lot)
                .filter(
                    Lot.seller_id == self.current_user["id"],
                    Lot.status == LotStatus.SOLD,
                )
                .count()
            )
            pending_lots = (
                db.query(Lot)
                .filter(
                    Lot.seller_id == self.current_user["id"],
                    Lot.status == LotStatus.PENDING,
                )
                .count()
            )

            stats_text = f"""
📊 Статистика продавца:

📦 Всего лотов: {total_lots}
✅ Активных: {active_lots}
💰 Проданных: {sold_lots}
⏳ На модерации: {pending_lots}
            """

            self.stats_label.setText(stats_text.strip())

            # Обновляем баланс продавца
            user = db.query(User).filter(User.id == self.current_user["id"]).first()
            if user:
                self.seller_balance_label.setText(f"{user.balance:,.2f} ₽")

        except Exception as e:
            logger.error(f"Ошибка при обновлении статистики: {e}")
        finally:
            db.close()

    def top_up_seller_balance(self):
        """Пополнить баланс продавца (ввод суммы через диалог)"""
        if not self.current_user:
            QMessageBox.warning(self, "Ошибка", "Необходимо авторизоваться")
            return
        amount, ok = QInputDialog.getDouble(
            self, "Пополнение баланса", "Сумма (₽):", 100.0, 1.0, 1_000_000.0, 2
        )
        if not ok:
            return
        if amount <= 0:
            QMessageBox.warning(self, "Ошибка", "Сумма должна быть больше 0")
            return
        success = finance_manager.add_balance(
            self.current_user["id"], amount, "Пополнение через панель продавца"
        )
        if success:
            QMessageBox.information(
                self, "Успех", f"Баланс пополнен на {amount:,.2f} ₽"
            )
            self.update_profile_stats()
            if hasattr(self.main_window, "refresh_system_stats"):
                self.main_window.refresh_system_stats()
        else:
            QMessageBox.critical(self, "Ошибка", "Не удалось пополнить баланс")

    def withdraw_seller_balance(self):
        """Вывести средства с баланса продавца (демо, без выплат)"""
        if not self.current_user:
            QMessageBox.warning(self, "Ошибка", "Необходимо авторизоваться")
            return
        amount, ok = QInputDialog.getDouble(
            self, "Вывод средств", "Сумма (₽):", 100.0, 1.0, 1_000_000.0, 2
        )
        if not ok:
            return
        if amount <= 0:
            QMessageBox.warning(self, "Ошибка", "Сумма должна быть больше 0")
            return
        success = finance_manager.deduct_balance(
            self.current_user["id"], amount, "Вывод средств (демо)"
        )
        if success:
            QMessageBox.information(self, "Успех", f"Списано {amount:,.2f} ₽")
            self.update_profile_stats()
            if hasattr(self.main_window, "refresh_system_stats"):
                self.main_window.refresh_system_stats()
        else:
            QMessageBox.critical(self, "Ошибка", "Недостаточно средств или ошибка")

    def show_context_menu(self, position):
        """Показывает контекстное меню для таблицы лотов"""
        if not self.current_user:
            return

        # Получаем индекс строки
        row = self.lots_table.rowAt(position.y())
        if row < 0:
            return

        # Получаем ID лота из первой колонки
        lot_id_item = self.lots_table.item(row, 0)
        if not lot_id_item:
            return

        try:
            lot_id = int(lot_id_item.text())

            # Получаем лот из базы данных
            db = SessionLocal()
            try:
                lot = db.query(Lot).filter(Lot.id == lot_id).first()
                if not lot or lot.seller_id != self.current_user["id"]:
                    return

                # Создаем контекстное меню
                menu = QMenu(self)

                # Действие "Просмотреть"
                view_action = menu.addAction("👁️ Просмотреть детали")
                view_action.triggered.connect(lambda: self.view_lot(lot))

                menu.addSeparator()

                # Действия в зависимости от статуса
                if lot.status == LotStatus.DRAFT:
                    edit_action = menu.addAction("✏️ Редактировать")
                    edit_action.triggered.connect(lambda: self.edit_lot(lot))

                    delete_action = menu.addAction("🗑️ Удалить")
                    delete_action.triggered.connect(lambda: self.delete_lot(lot))

                    submit_action = menu.addAction("📤 Отправить на модерацию")
                    submit_action.triggered.connect(
                        lambda: self.submit_lot_for_moderation(lot)
                    )

                elif lot.status == LotStatus.PENDING:
                    cancel_action = menu.addAction("❌ Отменить отправку")
                    cancel_action.triggered.connect(
                        partial(self.cancel_submission, lot)
                    )

                elif lot.status == LotStatus.ACTIVE:
                    delete_action = menu.addAction("🗑️ Удалить лот")
                    delete_action.triggered.connect(lambda: self.delete_active_lot(lot))

                # Экспорт
                menu.addSeparator()
                export_action = menu.addAction("📄 Экспорт лота")
                export_action.triggered.connect(lambda: self.export_lot_from_menu(lot))

                # Показываем меню
                menu.exec_(self.lots_table.mapToGlobal(position))

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Ошибка при показе контекстного меню: {e}")

    def export_lot_from_menu(self, lot: Lot):
        """Экспорт лота из контекстного меню"""
        try:
            pass

            # Предлагаем сохранить файл
            file_dialog = QFileDialog()
            file_dialog.setNameFilter("Текстовый файл (*.txt);;HTML файл (*.html)")
            file_dialog.setDefaultSuffix("txt")
            file_dialog.setAcceptMode(QFileDialog.AcceptSave)
            file_dialog.setWindowTitle(f"Экспорт лота: {lot.title}")

            if file_dialog.exec_():
                file_path = file_dialog.selectedFiles()[0]

                # Определяем формат по расширению
                format_type = "html" if file_path.endswith(".html") else "txt"
                content = DocumentGenerator.generate_lot_report(lot, format_type)

                # Сохраняем файл
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)

                QMessageBox.information(
                    self,
                    "Успех",
                    f"Лот '{lot.title}' экспортирован в файл:\n{file_path}",
                )

        except Exception as e:
            logger.error(f"Ошибка при экспорте лота: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка при экспорте: {e}")

    def on_tab_changed(self, index):
        """Обработчик переключения вкладок"""
        # Обновляем данные при переключении на вкладку профиля (индекс 2)
        if index == 2:  # Вкладка профиля
            self.update_profile_stats()
        # Обновляем данные при переключении на вкладку профиля (индекс 2)
        if index == 2:  # Вкладка профиля
            self.update_profile_stats()
