import os
import sys

# Добавляем корневую директорию в путь для импорта
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

# Прогрессивная система ставок (цена -> минимальный шаг)
# Схема: 1,2,5,10, затем 10,20,50,100 и так далее
BID_INCREMENT_RULES = {
    0: 1,  # 0-99₽ -> шаг 1₽
    100: 2,  # 100-499₽ -> шаг 2₽
    500: 5,  # 500-999₽ -> шаг 5₽
    1000: 10,  # 1000-4999₽ -> шаг 10₽
    5000: 20,  # 5000-9999₽ -> шаг 20₽
    10000: 50,  # 10000-49999₽ -> шаг 50₽
    50000: 100,  # 50000-99999₽ -> шаг 100₽
    100000: 200,  # 100000-499999₽ -> шаг 200₽
    500000: 500,  # 500000-999999₽ -> шаг 500₽
    1000000: 1000,  # 1000000-4999999₽ -> шаг 1000₽
    5000000: 2000,  # 5000000+₽ -> шаг 2000₽
}


def calculate_min_bid(current_price: float) -> float:
    """
    Рассчитывает минимальную ставку на основе текущей цены

    Args:
        current_price: Текущая цена лота

    Returns:
        float: Минимальная следующая ставка
    """
    # Находим подходящее правило
    min_increment = 1  # По умолчанию

    for price_threshold, increment in sorted(BID_INCREMENT_RULES.items()):
        if current_price >= price_threshold:
            min_increment = increment
        else:
            break

    return current_price + min_increment


def get_bid_increment_info(current_price: float) -> dict:
    """
    Возвращает информацию о правилах ставок для текущей цены

    Args:
        current_price: Текущая цена лота

    Returns:
        dict: Информация о минимальной ставке и правилах
    """
    min_bid = calculate_min_bid(current_price)
    increment = min_bid - current_price

    # Определяем диапазон цен для текущего правила
    current_rule = None
    next_rule = None

    sorted_rules = sorted(BID_INCREMENT_RULES.items())

    for i, (threshold, step) in enumerate(sorted_rules):
        if current_price >= threshold:
            current_rule = (threshold, step)
            if i + 1 < len(sorted_rules):
                next_rule = sorted_rules[i + 1]

    return {
        "current_price": current_price,
        "min_bid": min_bid,
        "increment": increment,
        "current_rule": current_rule,
        "next_rule": next_rule,
    }


def format_bid_info(current_price: float) -> str:
    """
    Форматирует информацию о ставках для отображения пользователю

    Args:
        current_price: Текущая цена лота

    Returns:
        str: Отформатированная информация
    """
    info = get_bid_increment_info(current_price)

    text = f"💰 <b>Текущая цена:</b> {current_price}₽\n"
    text += f"📈 <b>Минимальная ставка:</b> {info['min_bid']}₽\n"
    text += f"📊 <b>Шаг ставки:</b> {info['increment']}₽\n\n"

    if info["next_rule"]:
        next_threshold, next_step = info["next_rule"]
        text += f"ℹ️ При цене {next_threshold}₽ шаг увеличится до {next_step}₽"

    return text


def validate_bid(current_price: float, bid_amount: float) -> tuple[bool, str]:
    """
    Проверяет, является ли ставка валидной

    Args:
        current_price: Текущая цена лота
        bid_amount: Предлагаемая ставка

    Returns:
        tuple: (is_valid, error_message)
    """
    min_bid = calculate_min_bid(current_price)

    if bid_amount < min_bid:
        return False, f"Ставка должна быть не менее {min_bid}₽"

    if bid_amount <= current_price:
        return False, f"Ставка должна быть больше текущей цены ({current_price}₽)"

    return True, "Ставка принята"


def get_quick_bid_options(current_price: float) -> list[float]:
    """
    Возвращает варианты быстрых ставок

    Args:
        current_price: Текущая цена лота

    Returns:
        list: Список вариантов ставок
    """
    info = get_bid_increment_info(current_price)
    min_bid = info["min_bid"]
    increment = info["increment"]

    # Предлагаем 3 варианта: минимальная, +2 шага, +5 шагов
    options = [
        min_bid,  # Минимальная ставка
        min_bid + increment,  # +1 шаг
        min_bid + increment * 2,  # +2 шага
    ]

    # Добавляем еще один вариант для дорогих лотов
    if current_price >= 1000:
        options.append(min_bid + increment * 5)  # +5 шагов

    return options
