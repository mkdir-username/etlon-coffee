from aiogram.fsm.state import State, StatesGroup


class OrderState(StatesGroup):
    """FSM для оформления заказа клиентом"""
    browsing_menu = State()         # просмотр меню, добавление в корзину
    selecting_size = State()        # выбор размера напитка
    selecting_modifiers = State()   # выбор модификаторов (сиропы, молоко и т.д.)
    selecting_time = State()        # выбор времени забора
    applying_bonus = State()        # выбор списания баллов
    confirming = State()            # подтверждение заказа
    entering_comment = State()      # ввод комментария к позиции
