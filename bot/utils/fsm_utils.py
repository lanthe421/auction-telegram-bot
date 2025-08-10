"""
Утилиты для работы с FSM (Finite State Machine)
"""

import logging
from typing import Optional

from aiogram.fsm.context import FSMContext

logger = logging.getLogger(__name__)


async def clear_bid_state_if_needed(state: FSMContext) -> bool:
    """
    Очищает состояние FSM, если пользователь находится в состоянии ожидания ставки.

    Args:
        state: Контекст FSM

    Returns:
        bool: True если состояние было очищено, False если не было необходимости
    """
    try:
        current_state = await state.get_state()
        if current_state and "waiting_for_bid_amount" in current_state:
            await state.clear()
            logger.info(f"Очищено состояние FSM: {current_state}")
            return True
        return False
    except Exception as e:
        logger.error(f"Ошибка при очистке состояния FSM: {e}")
        return False


async def get_current_state_name(state: FSMContext) -> Optional[str]:
    """
    Получает название текущего состояния FSM.

    Args:
        state: Контекст FSM

    Returns:
        Optional[str]: Название состояния или None
    """
    try:
        return await state.get_state()
    except Exception as e:
        logger.error(f"Ошибка при получении состояния FSM: {e}")
        return None


async def is_in_bid_state(state: FSMContext) -> bool:
    """
    Проверяет, находится ли пользователь в состоянии ожидания ставки.

    Args:
        state: Контекст FSM

    Returns:
        bool: True если в состоянии ожидания ставки
    """
    current_state = await get_current_state_name(state)
    return current_state is not None and "waiting_for_bid_amount" in current_state
