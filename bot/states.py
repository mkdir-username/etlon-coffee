from aiogram.fsm.state import State, StatesGroup


class OrderState(StatesGroup):
    """FSM для оформления заказа клиентом"""
    browsing_menu = State()     # просмотр меню, добавление в корзину
    selecting_time = State()    # выбор времени забора
    confirming = State()        # подтверждение заказа
