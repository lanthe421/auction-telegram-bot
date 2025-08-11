from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot.utils.bid_calculator import get_quick_bid_options


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Главная клавиатура"""
    keyboard = [
        [KeyboardButton(text="🎯 Мое участие"), KeyboardButton(text="💰 Мои ставки")],
        [
            KeyboardButton(text="👤 Личный кабинет"),
            KeyboardButton(text="💳 Мой баланс"),
        ],
        [KeyboardButton(text="📋 История торгов")],
        [KeyboardButton(text="🆘 Поддержка"), KeyboardButton(text="⚙️ Настройки")],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_admin_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура администратора"""
    keyboard = [
        [KeyboardButton(text="📊 Статистика")],
        [
            KeyboardButton(text="👥 Управление пользователями"),
            KeyboardButton(text="💰 Финансы"),
        ],
        [KeyboardButton(text="📋 История торгов"), KeyboardButton(text="⚙️ Настройки")],
        [KeyboardButton(text="🔙 Главное меню")],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_support_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура системы поддержки"""
    keyboard = [
        [
            InlineKeyboardButton(
                text="📋 Лоты на модерации", callback_data="pending_lots"
            )
        ],
        [
            InlineKeyboardButton(
                text="📝 Жалобы на рассмотрении", callback_data="pending_complaints"
            )
        ],
        [
            InlineKeyboardButton(
                text="💬 Вопросы пользователей", callback_data="pending_questions"
            )
        ],
        [InlineKeyboardButton(text="✅ Одобрить лот", callback_data="approve_lot")],
        [InlineKeyboardButton(text="❌ Отклонить лот", callback_data="reject_lot")],
        [
            InlineKeyboardButton(
                text="🔍 Рассмотреть жалобу", callback_data="review_complaint"
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_complaint_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для жалоб"""
    keyboard = [
        [
            InlineKeyboardButton(
                text="📝 Подать жалобу", callback_data="submit_complaint"
            )
        ],
        [InlineKeyboardButton(text="📋 Мои жалобы", callback_data="my_complaints")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_auction_keyboard(lot_id: int) -> InlineKeyboardMarkup:
    """Клавиатура аукциона"""
    keyboard = [
        [InlineKeyboardButton(text="💰 Сделать ставку", callback_data=f"bid:{lot_id}")],
        [InlineKeyboardButton(text="📋 Детали лота", callback_data=f"lot:{lot_id}")],
        [
            InlineKeyboardButton(
                text="📞 Связаться с продавцом",
                callback_data=f"contact_seller:{lot_id}",
            )
        ],
        [
            InlineKeyboardButton(
                text="📄 Скачать файлы", callback_data=f"download_files:{lot_id}"
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_bid_keyboard(
    lot_id: int, current_price: float, user_id: int = None
) -> InlineKeyboardMarkup:
    """Клавиатура для ставок с быстрыми опциями"""
    quick_options = get_quick_bid_options(current_price)

    keyboard = []
    for option in quick_options:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"💰 {option:,.0f} ₽",
                    callback_data=f"quick_bid:{lot_id}:{option}",
                )
            ]
        )

    keyboard.extend(
        [
            [
                InlineKeyboardButton(
                    text="✏️ Своя сумма", callback_data=f"custom_bid:{lot_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🤖 Автоставка", callback_data=f"auto_bid:{lot_id}"
                )
            ],
        ]
    )

    # Кнопки для включения/выключения автоставок в интерфейсе ставок убраны по требованию

    keyboard.append(
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"lot_details:{lot_id}")]
    )

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_payment_keyboard(amount: float, lot_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для платежей"""
    keyboard = [
        [
            InlineKeyboardButton(
                text="💳 Банковская карта", callback_data=f"pay_card:{lot_id}"
            )
        ],
        [InlineKeyboardButton(text="📱 СБП", callback_data=f"pay_sbp:{lot_id}")],
        [
            InlineKeyboardButton(
                text="💳 Оплатить напрямую", callback_data=f"pay_balance:{lot_id}"
            )
        ],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_payment")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_confirmation_keyboard(action: str, item_id: int) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения"""
    keyboard = [
        [
            InlineKeyboardButton(
                text="✅ Подтвердить", callback_data=f"confirm:{action}:{item_id}"
            ),
            InlineKeyboardButton(text="❌ Отменить", callback_data="cancel"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_document_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа документа"""
    keyboard = [
        [
            InlineKeyboardButton(
                text="💎 Ювелирные изделия", callback_data="doc_type:jewelry"
            )
        ],
        [
            InlineKeyboardButton(
                text="🏛️ Исторические ценности", callback_data="doc_type:historical"
            )
        ],
        [
            InlineKeyboardButton(
                text="📦 Стандартные лоты", callback_data="doc_type:standard"
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_user_profile_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура профиля пользователя"""
    keyboard = [
        [
            InlineKeyboardButton(
                text="💳 Информация об оплате", callback_data="top_up_balance"
            )
        ],
        [
            InlineKeyboardButton(text="➕ Пополнить", callback_data="start_top_up"),
            InlineKeyboardButton(text="➖ Вывести", callback_data="start_withdraw"),
        ],
        [InlineKeyboardButton(text="🎯 Мое участие", callback_data="my_participation")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="user_stats")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_lot_management_keyboard(lot_id: int) -> InlineKeyboardMarkup:
    """Клавиатура управления лотом"""
    keyboard = [
        [
            InlineKeyboardButton(
                text="✏️ Редактировать", callback_data=f"edit_lot:{lot_id}"
            )
        ],
        [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_lot:{lot_id}")],
        [
            InlineKeyboardButton(
                text="⏸️ Приостановить", callback_data=f"pause_lot:{lot_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="📊 Статистика лота", callback_data=f"lot_stats:{lot_id}"
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
