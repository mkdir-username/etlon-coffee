from typing import Any

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.models import MenuItem, CartItem, Order, OrderStatus


def size_keyboard(
    menu_item_id: int,
    item_name: str,
    base_price: int,
    sizes: list[dict[str, Any]]
) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора размера напитка.
    sizes: [{"size": "S", "size_name": "Маленький 250мл", "price_diff": 0}, ...]
    """
    builder = InlineKeyboardBuilder()

    for s in sizes:
        diff = s["price_diff"]
        diff_str = f"+{diff}р" if diff > 0 else ""
        final_price = base_price + diff
        # S — Маленький 250мл (220р)
        text = f"{s['size']} — {s['size_name']} ({final_price}р) {diff_str}".strip()
        builder.button(
            text=text,
            callback_data=f"size:{menu_item_id}:{s['size']}"
        )

    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="<- Назад", callback_data="size:back"))
    return builder.as_markup()


# Названия категорий модификаторов
MODIFIER_CATEGORY_NAMES = {
    "syrup": "Сиропы",
    "milk": "Молоко",
    "extra": "Дополнительно",
}


def modifiers_keyboard(
    menu_item_id: int,
    size: str | None,
    modifiers: list[dict[str, Any]],
    selected_ids: list[int]
) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора модификаторов.
    Формат кнопки: "✓ Ванильный сироп +50₽" или "○ Ванильный сироп +50₽"
    callback_data: mod:toggle:{menu_item_id}:{size}:{modifier_id}

    + кнопка "Готово →" (mod:done:{menu_item_id}:{size})
    + кнопка "← Назад" (mod:back:{menu_item_id})
    """
    builder = InlineKeyboardBuilder()
    selected_set = set(selected_ids)
    size_str = size or "none"

    # Группируем по категориям
    by_category: dict[str, list[dict[str, Any]]] = {}
    for mod in modifiers:
        cat = mod["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(mod)

    # Выводим по категориям
    for category in ["syrup", "milk", "extra"]:
        if category not in by_category:
            continue
        cat_name = MODIFIER_CATEGORY_NAMES.get(category, category)
        # Заголовок категории (неактивная кнопка)
        builder.button(
            text=f"— {cat_name} —",
            callback_data=f"mod:noop:{menu_item_id}"
        )
        builder.adjust(1)

        for mod in by_category[category]:
            is_selected = mod["id"] in selected_set
            marker = "✓" if is_selected else "○"
            text = f"{marker} {mod['name']} +{mod['price']}₽"
            builder.button(
                text=text,
                callback_data=f"mod:toggle:{menu_item_id}:{size_str}:{mod['id']}"
            )

    builder.adjust(1)

    # Итоговая цена модификаторов
    total_mod_price = sum(mod["price"] for mod in modifiers if mod["id"] in selected_set)
    done_text = "Готово →" if total_mod_price == 0 else f"Готово (+{total_mod_price}₽) →"

    builder.row(
        InlineKeyboardButton(text="← Назад", callback_data=f"mod:back:{menu_item_id}"),
        InlineKeyboardButton(text=done_text, callback_data=f"mod:done:{menu_item_id}:{size_str}"),
    )
    return builder.as_markup()


def menu_keyboard(
    menu: list[MenuItem],
    cart: list[CartItem],
    favorite_ids: set[int] | None = None
) -> InlineKeyboardMarkup:
    """Клавиатура меню с возможностью добавления в корзину"""
    builder = InlineKeyboardBuilder()
    favorite_ids = favorite_ids or set()

    # кол-во каждой позиции в корзине
    cart_counts = {item.menu_item_id: item.quantity for item in cart}

    for item in menu:
        count = cart_counts.get(item.id, 0)
        count_str = f" [{count}]" if count > 0 else ""
        fav_marker = " *" if item.id in favorite_ids else ""
        builder.button(
            text=f"{fav_marker}{item.name} — {item.price}р{count_str}",
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


def _cart_item_key(item: CartItem) -> str:
    """Уникальный ключ для позиции корзины: menu_item_id + size + modifier_ids"""
    parts = [str(item.menu_item_id)]
    if item.size:
        parts.append(item.size)
    else:
        parts.append("none")
    # Сортируем modifier_ids для консистентности
    if item.modifier_ids:
        parts.append("-".join(str(mid) for mid in sorted(item.modifier_ids)))
    else:
        parts.append("none")
    return ":".join(parts)


def cart_keyboard(cart: list[CartItem]) -> InlineKeyboardMarkup:
    """Клавиатура корзины"""
    builder = InlineKeyboardBuilder()

    for item in cart:
        comment_btn = "📝" if item.comment else "✏️"
        cart_key = _cart_item_key(item)
        # Название с размером: Латте (M) x1
        size_suffix = f" ({item.size})" if item.size else ""
        # Добавляем индикатор модификаторов
        mod_indicator = " +" if item.modifier_ids else ""
        display_name = f"{item.name}{size_suffix}{mod_indicator}"

        builder.row(
            InlineKeyboardButton(text="−", callback_data=f"cart:dec:{cart_key}"),
            InlineKeyboardButton(
                text=f"{display_name} x{item.quantity}",
                callback_data=f"cart:info:{cart_key}"
            ),
            InlineKeyboardButton(text="+", callback_data=f"cart:inc:{cart_key}"),
            InlineKeyboardButton(text=comment_btn, callback_data=f"cart:comment:{cart_key}"),
        )

    builder.row(
        InlineKeyboardButton(text="<- Меню", callback_data="cart:back"),
        InlineKeyboardButton(text="Оформить ->", callback_data="cart:checkout"),
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


def menu_manage_keyboard(items: list[MenuItem]) -> InlineKeyboardMarkup:
    """
    Клавиатура управления меню для баристы.
    Показывает все позиции с текущим статусом.
    """
    builder = InlineKeyboardBuilder()

    for item in items:
        if item.available:
            text = f"✅ {item.name} — {item.price}₽"
        else:
            text = f"❌ {item.name} — {item.price}₽ (скрыто)"
        builder.button(text=text, callback_data=f"menu_toggle:{item.id}")

    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="🔄 Обновить", callback_data="menu_manage:refresh"))
    return builder.as_markup()


# ===== HISTORY =====

def history_keyboard(orders: list[Order], page: int, has_next: bool) -> InlineKeyboardMarkup:
    """Клавиатура истории заказов с пагинацией"""
    builder = InlineKeyboardBuilder()

    for order in orders:
        status_emoji = {
            OrderStatus.PENDING: "⏳",
            OrderStatus.CONFIRMED: "📋",
            OrderStatus.PREPARING: "🔄",
            OrderStatus.READY: "✅",
            OrderStatus.COMPLETED: "✅",
            OrderStatus.CANCELLED: "❌",
        }.get(order.status, "")

        # summary: первые 2 позиции
        items_summary = ", ".join(
            f"{item.name}" + (f" x{item.quantity}" if item.quantity > 1 else "")
            for item in order.items[:2]
        )
        if len(order.items) > 2:
            items_summary += "..."

        builder.button(
            text=f"#{order.id} — {items_summary} — {order.total}р {status_emoji}",
            callback_data=f"history:view:{order.id}"
        )

    builder.adjust(1)

    # пагинация
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="←", callback_data=f"history:page:{page - 1}"))
    if has_next:
        nav_buttons.append(InlineKeyboardButton(text="→", callback_data=f"history:page:{page + 1}"))
    if nav_buttons:
        builder.row(*nav_buttons)

    return builder.as_markup()


def order_detail_keyboard(
    order_id: int,
    order: Order | None = None,
    user_id: int | None = None
) -> InlineKeyboardMarkup:
    """Клавиатура деталей заказа с кнопками повтора и отмены"""
    builder = InlineKeyboardBuilder()

    # Кнопка повтора всегда доступна
    builder.button(text="🔄 Повторить заказ", callback_data=f"repeat:{order_id}")

    # Кнопка отмены доступна только для CONFIRMED и владельцу
    if order and user_id and order.status == OrderStatus.CONFIRMED and order.user_id == user_id:
        builder.button(text="Отменить", callback_data=f"cancel:{order_id}")

    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="<- К списку", callback_data="history:back"))
    return builder.as_markup()


# ===== FAVORITES =====

def favorites_keyboard(items: list[MenuItem]) -> InlineKeyboardMarkup:
    """Клавиатура избранных позиций"""
    builder = InlineKeyboardBuilder()

    for item in items:
        # ряд: [+ В корзину] [название — цена] [x удалить]
        builder.row(
            InlineKeyboardButton(text="+", callback_data=f"fav:order:{item.id}"),
            InlineKeyboardButton(
                text=f"* {item.name} — {item.price}р",
                callback_data=f"fav:info:{item.id}"
            ),
            InlineKeyboardButton(text="x", callback_data=f"fav:remove:{item.id}"),
        )

    builder.row(InlineKeyboardButton(text="Новый заказ /start", callback_data="fav:start"))
    return builder.as_markup()


def menu_item_detail_keyboard(item_id: int, is_favorite: bool) -> InlineKeyboardMarkup:
    """Клавиатура детали позиции меню с toggle избранного"""
    builder = InlineKeyboardBuilder()

    if is_favorite:
        builder.button(text="Убрать из избранного", callback_data=f"fav:remove:{item_id}")
    else:
        builder.button(text="* Добавить в избранное", callback_data=f"fav:add:{item_id}")

    builder.row(InlineKeyboardButton(text="<- Назад", callback_data="menu:back"))
    return builder.as_markup()


# ===== BONUS =====

def bonus_keyboard(user_points: int, max_redeem: int, order_total: int) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора списания баллов.
    Показывает варианты: пропустить, фиксированные суммы, максимум.
    """
    builder = InlineKeyboardBuilder()

    # Фиксированные варианты: 50, 100, 150, 200
    fixed_amounts = [50, 100, 150, 200]
    available_amounts = [a for a in fixed_amounts if a <= user_points and a <= max_redeem]

    for amount in available_amounts:
        builder.button(text=f"Списать {amount} баллов (-{amount}р)", callback_data=f"bonus:use:{amount}")

    # Максимум если отличается от фиксированных
    if max_redeem > 0 and max_redeem not in available_amounts:
        builder.button(text=f"Максимум: {max_redeem} баллов (-{max_redeem}р)", callback_data="bonus:max")

    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="Пропустить", callback_data="bonus:skip"))

    return builder.as_markup()
