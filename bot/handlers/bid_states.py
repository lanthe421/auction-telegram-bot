from aiogram.fsm.state import State, StatesGroup


class BidStates(StatesGroup):
    waiting_for_bid_amount = State()
    waiting_for_max_bid_amount = State()


class BalanceStates(StatesGroup):
    waiting_for_top_up_amount = State()
    waiting_for_withdraw_amount = State()
