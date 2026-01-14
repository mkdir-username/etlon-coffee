from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.models import MenuItem, CartItem, Order, OrderStatus


def menu_keyboard(menu: list[MenuItem], cart: list[CartItem]) -> InlineKeyboardMarkup:
    """Клавиатура меню с возможностью добавления в корзину"""
    builder = InlineKeyboardBuilder()

    # кол-во каждой позиции в корзине
    cart_counts = {item.menu_item_id: item.quantity for item in cart}

    for item in menu:
        count = cart_counts.get(item.id, 0)
        count_str = f" [{count}]" if count > 0 else ""
        builder.button(
            text=f"{item.name} — {item.price}р{count_str}",
            callback_data=f"menu:{item.id}"
        )

    builder.adjust(1)  # по одной кнопке в ряд

    # кнопка корзины
    if cart:
        total = sum(i.price * i.quantity for i in cart)
        builder.row(
            InlineKeyboardButton(
                text=f"Корзина ({total}р) →",
                callback_data="cart:show"
            )
        )

    return builder.as_markup()


def cart_keyboard(cart: list[CartItem]) -> InlineKeyboardMarkup:
    """Клавиатура корзины"""
    builder = InlineKeyboardBuilder()

    for item in cart:
        builder.row(
            InlineKeyboardButton(text="−", callback_data=f"cart:dec:{item.menu_item_id}"),
            InlineKeyboardButton(
                text=f"{item.name} x{item.quantity}",
                callback_data=f"cart:info:{item.menu_item_id}"
            ),
            InlineKeyboardButton(text="+", callback_data=f"cart:inc:{item.menu_item_id}"),
        )

    builder.row(
        InlineKeyboardButton(text="← Меню", callback_data="cart:back"),
        InlineKeyboardButton(text="Оформить →", callback_data="cart:checkout"),
    )

    return builder.as_markup()


def pickup_time_keyboard() -> InlineKeyboardMarkup:
    """Выбор времени забора"""
    builder = InlineKeyboardBuilder()
    times = [
        ("Через 10 мин", "time:10"),
        ("Через 15 мин", "time:15"),
        ("Через 20 мин", "time:20"),
        ("Через 30 мин", "time:30"),
    ]
    for text, cb in times:
        builder.button(text=text, callback_data=cb)
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="time:back"))
    return builder.as_markup()


def confirm_keyboard() -> InlineKeyboardMarkup:
    """Подтверждение заказа"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="← Изменить", callback_data="confirm:edit"),
            InlineKeyboardButton(text="Подтвердить", callback_data="confirm:yes"),
        ]
    ])


# ===== BARISTA =====

def barista_orders_keyboard(orders: list[Order]) -> InlineKeyboardMarkup:
    """Список заказов для бариста"""
    builder = InlineKeyboardBuilder()

    if not orders:
        builder.button(text="Нет активных заказов", callback_data="barista:refresh")
    else:
        for order in orders:
            status_emoji = {
                OrderStatus.CONFIRMED: "",
                OrderStatus.PREPARING: "",
                OrderStatus.READY: "",
            }.get(order.status, "")

            builder.button(
                text=f"{status_emoji} #{order.id} — {order.pickup_time}",
                callback_data=f"barista:order:{order.id}"
            )

    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="Обновить", callback_data="barista:refresh"))
    return builder.as_markup()


def barista_order_detail_keyboard(order: Order) -> InlineKeyboardMarkup:
    """Детали заказа и смена статуса"""
    builder = InlineKeyboardBuilder()

    # кнопки перехода статуса
    if order.status == OrderStatus.CONFIRMED:
        builder.button(text="Начать готовить", callback_data=f"barista:status:{order.id}:preparing")
    elif order.status == OrderStatus.PREPARING:
        builder.button(text="Готов к выдаче", callback_data=f"barista:status:{order.id}:ready")
    elif order.status == OrderStatus.READY:
        builder.button(text="Выдан", callback_data=f"barista:status:{order.id}:completed")

    builder.row(InlineKeyboardButton(text="← К списку", callback_data="barista:list"))
    return builder.as_markup()
