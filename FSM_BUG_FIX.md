# 🐛 Исправление бага с застреванием в состоянии FSM

## 📋 Описание проблемы

### 🐛 БАГ

Пользователь нажимает кнопку **"Ввести свою сумму"** для создания ставки, но не вводит сумму и нажимает **"Назад к лоту"**. Состояние FSM (Finite State Machine) не очищается, и любая следующая команда (например, `/support`, `/start`, `/my_bids`) воспринимается ботом как попытка ввести ставку, что приводит к ошибке **"Неверный формат суммы"**.

### 🔄 Сценарий воспроизведения

1. Пользователь нажимает "Ввести свою сумму"
2. Бот переводит в состояние `BidStates.waiting_for_bid_amount`
3. Пользователь НЕ вводит сумму
4. Пользователь нажимает "Назад к лоту"
5. Состояние FSM НЕ очищается
6. Пользователь вводит команду `/support`
7. Бот воспринимает `/support` как ставку
8. Бот выводит ошибку "Неверный формат суммы"

## 🛠️ Решение

### ✅ Создана утилита для работы с FSM

**Файл:** `bot/utils/fsm_utils.py`

```python
async def clear_bid_state_if_needed(state: FSMContext) -> bool:
    """Очищает состояние FSM, если пользователь находится в состоянии ожидания ставки."""

async def get_current_state_name(state: FSMContext) -> Optional[str]:
    """Получает название текущего состояния FSM."""

async def is_in_bid_state(state: FSMContext) -> bool:
    """Проверяет, находится ли пользователь в состоянии ожидания ставки."""
```

### ✅ Добавлена очистка состояния в ключевые обработчики

#### 1. Кнопка "Назад к лоту"

**Файл:** `bot/handlers/auction.py`

```python
@router.callback_query(F.data.startswith("lot_details:"))
async def show_lot_details_from_back_button(callback: CallbackQuery, state: FSMContext):
    # Очищаем состояние FSM, если пользователь был в процессе ввода ставки
    from bot.utils.fsm_utils import clear_bid_state_if_needed
    if await clear_bid_state_if_needed(state):
        logger.info(f"Очищено состояние FSM для пользователя {callback.from_user.id}")
```

#### 2. Команда `/start`

**Файл:** `bot/handlers/auction.py`

```python
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    # Очищаем состояние FSM, если пользователь был в процессе ввода ставки
    from bot.utils.fsm_utils import clear_bid_state_if_needed
    if await clear_bid_state_if_needed(state):
        logger.info(f"Очищено состояние FSM для пользователя {message.from_user.id}")
```

#### 3. Команда `/support`

**Файл:** `bot/handlers/support.py`

```python
@router.message(Command("support"))
async def support_command(message: Message, state: FSMContext):
    # Очищаем состояние FSM, если пользователь был в процессе ввода ставки
    from bot.utils.fsm_utils import clear_bid_state_if_needed
    if await clear_bid_state_if_needed(state):
        logger.info(f"Очищено состояние FSM для пользователя {message.from_user.id}")
```

#### 4. Команда `/my_bids`

**Файл:** `bot/handlers/bids.py`

```python
@router.message(Command("my_bids"))
async def my_bids(message: Message, state: FSMContext):
    # Очищаем состояние FSM, если пользователь был в процессе ввода ставки
    from bot.utils.fsm_utils import clear_bid_state_if_needed
    if await clear_bid_state_if_needed(state):
        logger.info(f"Очищено состояние FSM для пользователя {message.from_user.id}")
```

## 📊 Логирование

Все операции очистки состояния логируются:

```
INFO - Очищено состояние FSM: BidStates:waiting_for_bid_amount
INFO - Очищено состояние FSM для пользователя 123456789 при нажатии 'Назад к лоту'
INFO - Очищено состояние FSM для пользователя 123456789 при команде /support
```

## 🧪 Тестирование

### ✅ Проверено исправление

1. **Нажатие "Ввести свою сумму"** → состояние устанавливается
2. **Нажатие "Назад к лоту"** → состояние очищается
3. **Ввод команды `/support`** → команда работает корректно
4. **Ввод команды `/start`** → команда работает корректно
5. **Ввод команды `/my_bids`** → команда работает корректно

### ✅ Результат

- ❌ **До исправления:** Ошибка "Неверный формат суммы"
- ✅ **После исправления:** Команды работают корректно

## 🚀 Преимущества решения

1. **Автоматическая очистка** - не требует ручного вмешательства
2. **Централизованная логика** - одна функция для всех обработчиков
3. **Безопасность** - проверка состояния перед очисткой
4. **Логирование** - отслеживание всех операций очистки
5. **Масштабируемость** - легко добавить в новые обработчики

## 📁 Затронутые файлы

- ✅ `bot/utils/fsm_utils.py` - новая утилита
- ✅ `bot/utils/__init__.py` - добавлены экспорты
- ✅ `bot/handlers/auction.py` - очистка в кнопке "Назад" и /start
- ✅ `bot/handlers/support.py` - очистка в /support
- ✅ `bot/handlers/bids.py` - очистка в /my_bids

---

**🐛 БАГ ИСПРАВЛЕН!** ✅

Теперь пользователи могут безопасно использовать кнопку "Назад к лоту" без застревания в состоянии ожидания ставки.
