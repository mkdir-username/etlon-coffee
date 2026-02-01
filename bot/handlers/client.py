import asyncio
import html
import logging
from typing import Any

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InaccessibleMessage
from aiogram.fsm.context import FSMContext

from bot import database as db
from bot import loyalty
from bot.config import settings
from bot.models import CartItem, Order, OrderItem, OrderStatus
from bot.states import OrderState
from bot.keyboards import (
    menu_keyboard,
    cart_keyboard,
    pickup_time_keyboard,
    confirm_keyboard,
    history_keyboard,
    order_detail_keyboard,
    favorites_keyboard,
    bonus_keyboard,
    size_keyboard,
    modifiers_keyboard,
)

logger = logging.getLogger(__name__)

router = Router(name="client")


# ===== HELPERS =====

def _get_editable_message(callback: CallbackQuery) -> Message | None:
    """Возвращает сообщение если оно доступно для редактирования."""
    if not callback.message:
        return None
    if isinstance(callback.message, InaccessibleMessage):
        return None
    return callback.message


# ===== START =====

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    await state.clear()
    await state.set_state(OrderState.browsing_menu)
    await state.update_data(cart=[])

    menu = await db.get_menu()
    favorite_ids = await db.get_user_favorite_ids(message.from_user.id)
    await message.answer(
        "Привет! Это Etlon Coffee\n\n"
        "Выбери напитки из меню:",
        reply_markup=menu_keyboard(menu, [], favorite_ids)
    )


# ===== MENU =====

@router.callback_query(F.data.startswith("menu:"), OrderState.browsing_menu)
async def add_to_cart(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.data:
        await callback.answer()
        return
    msg = _get_editable_message(callback)
    if not msg:
        await callback.answer("Сообщение недоступно")
        return

    parts = callback.data.split(":")
    if parts[1] == "back":
        return

    item_id = int(parts[1])
    item = await db.get_menu_item(item_id)

    if not item or not item.available:
        logger.warning(
            "item_unavailable",
            extra={"user_id": callback.from_user.id, "item_id": item_id}
        )
        await callback.answer("Позиция недоступна")
        return

    sizes = await db.get_menu_item_sizes(item_id)

    if sizes:
        await state.update_data(selecting_item_id=item_id)
        await state.set_state(OrderState.selecting_size)

        logger.debug(
            "size_selection_started",
            extra={
                "user_id": callback.from_user.id,
                "item_id": item_id,
                "item_name": item.name,
                "sizes_count": len(sizes)
            }
        )

        await msg.edit_text(
            f"Выбери размер для {item.name}:",
            reply_markup=size_keyboard(item_id, item.name, item.price, sizes)
        )
        await callback.answer()
        return

    modifiers = await db.get_available_modifiers(item_id)

    if modifiers:
        await state.update_data(
            selecting_item_id=item_id,
            selecting_size=None,
            selecting_size_name=None,
            selecting_price=item.price,
            selected_modifiers=[]
        )
        await state.set_state(OrderState.selecting_modifiers)

        logger.debug(
            "modifiers_selection_started",
            extra={
                "user_id": callback.from_user.id,
                "item_id": item_id,
                "item_name": item.name,
                "modifiers_count": len(modifiers)
            }
        )

        await msg.edit_text(
            f"{item.name}\n"
            f"Цена: {item.price}₽\n\n"
            "Добавить что-нибудь?",
            reply_markup=modifiers_keyboard(item_id, None, modifiers, [])
        )
        await callback.answer()
        return

    data = await state.get_data()
    cart: list[dict[str, Any]] = data.get("cart", [])

    found = False
    for c in cart:
        if (c["menu_item_id"] == item_id
                and c.get("size") is None
                and not c.get("modifier_ids")):
            c["quantity"] += 1
            found = True
            break

    if not found:
        cart.append({
            "menu_item_id": item.id,
            "name": item.name,
            "price": item.price,
            "quantity": 1
        })

    await state.update_data(cart=cart)

    logger.debug(
        "cart_add",
        extra={
            "user_id": callback.from_user.id,
            "item_id": item_id,
            "item_name": item.name,
            "quantity": cart[-1]["quantity"]
        }
    )

    cart_items = [CartItem(**c) for c in cart]
    menu = await db.get_menu()
    favorite_ids = await db.get_user_favorite_ids(callback.from_user.id)

    await msg.edit_reply_markup(
        reply_markup=menu_keyboard(menu, cart_items, favorite_ids)
    )
    await callback.answer(f"{item.name} добавлен")


# ===== SIZE SELECTION =====

@router.callback_query(F.data.startswith("size:"), OrderState.selecting_size)
async def select_size(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработка выбора размера напитка"""
    if not callback.data:
        await callback.answer()
        return
    msg = _get_editable_message(callback)
    if not msg:
        await callback.answer("Сообщение недоступно")
        return

    parts = callback.data.split(":")

    if parts[1] == "back":
        await state.set_state(OrderState.browsing_menu)
        await state.update_data(selecting_item_id=None)

        data = await state.get_data()
        cart = [CartItem(**c) for c in data.get("cart", [])]
        menu = await db.get_menu()
        favorite_ids = await db.get_user_favorite_ids(callback.from_user.id)

        await msg.edit_text(
            "Выбери напитки из меню:",
            reply_markup=menu_keyboard(menu, cart, favorite_ids)
        )
        await callback.answer()
        return

    menu_item_id = int(parts[1])
    size = parts[2]

    sizes = await db.get_menu_item_sizes(menu_item_id)
    size_data = next((s for s in sizes if s["size"] == size), None)

    if not size_data:
        logger.warning(
            "size_not_found",
            extra={"user_id": callback.from_user.id, "menu_item_id": menu_item_id, "size": size}
        )
        await callback.answer("Размер недоступен")
        return

    item = await db.get_menu_item(menu_item_id)
    if not item:
        await callback.answer("Позиция недоступна")
        return

    final_price = item.price + size_data["price_diff"]

    modifiers = await db.get_available_modifiers(menu_item_id)

    if modifiers:
        await state.update_data(
            selecting_item_id=menu_item_id,
            selecting_size=size,
            selecting_size_name=size_data["size_name"],
            selecting_price=final_price,
            selected_modifiers=[]
        )
        await state.set_state(OrderState.selecting_modifiers)

        logger.debug(
            "modifiers_selection_started",
            extra={
                "user_id": callback.from_user.id,
                "item_id": menu_item_id,
                "item_name": item.name,
                "size": size,
                "modifiers_count": len(modifiers)
            }
        )

        size_display = f" ({size_data['size_name']})" if size else ""
        await msg.edit_text(
            f"{item.name}{size_display}\n"
            f"Базовая цена: {final_price}₽\n\n"
            "Добавить что-нибудь?",
            reply_markup=modifiers_keyboard(menu_item_id, size, modifiers, [])
        )
        await callback.answer()
        return

    data = await state.get_data()
    cart_data: list[dict[str, Any]] = data.get("cart", [])

    found = False
    for c in cart_data:
        if (c["menu_item_id"] == menu_item_id
                and c.get("size") == size
                and not c.get("modifier_ids")):
            c["quantity"] += 1
            found = True
            break

    if not found:
        cart_data.append({
            "menu_item_id": item.id,
            "name": item.name,
            "price": final_price,
            "quantity": 1,
            "size": size,
            "size_name": size_data["size_name"]
        })

    await state.update_data(cart=cart_data, selecting_item_id=None)
    await state.set_state(OrderState.browsing_menu)

    logger.debug(
        "cart_add_with_size",
        extra={
            "user_id": callback.from_user.id,
            "item_id": menu_item_id,
            "item_name": item.name,
            "size": size,
            "price": final_price
        }
    )

    cart_items = [CartItem(**c) for c in cart_data]
    menu = await db.get_menu()
    favorite_ids = await db.get_user_favorite_ids(callback.from_user.id)

    await msg.edit_text(
        "Выбери напитки из меню:",
        reply_markup=menu_keyboard(menu, cart_items, favorite_ids)
    )
    await callback.answer(f"{item.name} ({size}) добавлен")


# ===== MODIFIERS SELECTION =====

@router.callback_query(F.data.startswith("mod:noop:"), OrderState.selecting_modifiers)
async def modifier_noop(callback: CallbackQuery) -> None:
    """Заглушка для заголовков категорий"""
    await callback.answer()


@router.callback_query(F.data.startswith("mod:toggle:"), OrderState.selecting_modifiers)
async def toggle_modifier(callback: CallbackQuery, state: FSMContext) -> None:
    """Toggle модификатора в списке выбранных"""
    if not callback.data:
        await callback.answer()
        return
    msg = _get_editable_message(callback)
    if not msg:
        await callback.answer("Сообщение недоступно")
        return

    parts = callback.data.split(":")
    menu_item_id = int(parts[2])
    size_str = parts[3]
    modifier_id = int(parts[4])

    size = size_str if size_str != "none" else None

    data = await state.get_data()
    selected: list[int] = data.get("selected_modifiers", [])

    if modifier_id in selected:
        selected.remove(modifier_id)
        logger.debug(
            "modifier_deselected",
            extra={
                "user_id": callback.from_user.id,
                "menu_item_id": menu_item_id,
                "modifier_id": modifier_id
            }
        )
    else:
        selected.append(modifier_id)
        logger.debug(
            "modifier_selected",
            extra={
                "user_id": callback.from_user.id,
                "menu_item_id": menu_item_id,
                "modifier_id": modifier_id
            }
        )

    await state.update_data(selected_modifiers=selected)

    modifiers = await db.get_available_modifiers(menu_item_id)
    item = await db.get_menu_item(menu_item_id)

    if not item:
        await callback.answer("Позиция недоступна")
        return

    size_display = f" ({data.get('selecting_size_name')})" if data.get("selecting_size_name") else ""
    base_price = data.get("selecting_price", item.price)

    selected_mods = [m for m in modifiers if m["id"] in selected]
    total_mod_price = sum(m["price"] for m in selected_mods)

    await msg.edit_text(
        f"{item.name}{size_display}\n"
        f"Базовая цена: {base_price}₽\n"
        + (f"Модификаторы: +{total_mod_price}₽\n" if total_mod_price > 0 else "")
        + f"\nДобавить что-нибудь?",
        reply_markup=modifiers_keyboard(menu_item_id, size, modifiers, selected)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mod:done:"), OrderState.selecting_modifiers)
async def modifiers_done(callback: CallbackQuery, state: FSMContext) -> None:
    """Завершение выбора модификаторов — добавить в корзину"""
    if not callback.data:
        await callback.answer()
        return
    msg = _get_editable_message(callback)
    if not msg:
        await callback.answer("Сообщение недоступно")
        return

    parts = callback.data.split(":")
    menu_item_id = int(parts[2])
    size_str = parts[3]

    size = size_str if size_str != "none" else None

    data = await state.get_data()
    selected: list[int] = data.get("selected_modifiers", [])
    base_price = data.get("selecting_price", 0)
    size_name = data.get("selecting_size_name")

    item = await db.get_menu_item(menu_item_id)
    if not item:
        await callback.answer("Позиция недоступна")
        return

    modifier_names: list[str] = []
    modifiers_price = 0

    if selected:
        mods_data = await db.get_modifiers_by_ids(selected)
        modifier_names = [m["name"] for m in mods_data]
        modifiers_price = sum(m["price"] for m in mods_data)

    final_price = base_price + modifiers_price

    cart: list[dict[str, Any]] = data.get("cart", [])

    found = False
    sorted_selected = sorted(selected)
    for c in cart:
        if (c["menu_item_id"] == menu_item_id
                and c.get("size") == size
                and sorted(c.get("modifier_ids", [])) == sorted_selected):
            c["quantity"] += 1
            found = True
            break

    if not found:
        cart.append({
            "menu_item_id": item.id,
            "name": item.name,
            "price": final_price,
            "quantity": 1,
            "size": size,
            "size_name": size_name,
            "modifier_ids": selected,
            "modifier_names": modifier_names,
            "modifiers_price": modifiers_price,
        })

    await state.update_data(
        cart=cart,
        selecting_item_id=None,
        selecting_size=None,
        selecting_size_name=None,
        selecting_price=None,
        selected_modifiers=[]
    )
    await state.set_state(OrderState.browsing_menu)

    logger.info(
        "cart_add_with_modifiers",
        extra={
            "user_id": callback.from_user.id,
            "item_id": menu_item_id,
            "item_name": item.name,
            "size": size,
            "modifier_ids": selected,
            "modifiers_price": modifiers_price,
            "final_price": final_price
        }
    )

    cart_items = [CartItem(**c) for c in cart]
    menu = await db.get_menu()
    favorite_ids = await db.get_user_favorite_ids(callback.from_user.id)

    size_suffix = f" ({size})" if size else ""
    mod_suffix = f" +{len(selected)} доп." if selected else ""

    await msg.edit_text(
        "Выбери напитки из меню:",
        reply_markup=menu_keyboard(menu, cart_items, favorite_ids)
    )
    await callback.answer(f"{item.name}{size_suffix}{mod_suffix} добавлен")


@router.callback_query(F.data.startswith("mod:back:"), OrderState.selecting_modifiers)
async def modifiers_back(callback: CallbackQuery, state: FSMContext) -> None:
    """Возврат из выбора модификаторов"""
    if not callback.data:
        await callback.answer()
        return
    msg = _get_editable_message(callback)
    if not msg:
        await callback.answer("Сообщение недоступно")
        return

    parts = callback.data.split(":")
    menu_item_id = int(parts[2])

    data = await state.get_data()
    size = data.get("selecting_size")

    item = await db.get_menu_item(menu_item_id)
    if not item:
        await state.set_state(OrderState.browsing_menu)
        cart = [CartItem(**c) for c in data.get("cart", [])]
        menu = await db.get_menu()
        favorite_ids = await db.get_user_favorite_ids(callback.from_user.id)
        await msg.edit_text(
            "Выбери напитки из меню:",
            reply_markup=menu_keyboard(menu, cart, favorite_ids)
        )
        await callback.answer()
        return

    sizes = await db.get_menu_item_sizes(menu_item_id)
    if sizes and size is not None:
        await state.set_state(OrderState.selecting_size)
        await state.update_data(
            selecting_item_id=menu_item_id,
            selected_modifiers=[]
        )
        await msg.edit_text(
            f"Выбери размер для {item.name}:",
            reply_markup=size_keyboard(menu_item_id, item.name, item.price, sizes)
        )
        await callback.answer()
        return

    await state.set_state(OrderState.browsing_menu)
    await state.update_data(
        selecting_item_id=None,
        selecting_size=None,
        selecting_size_name=None,
        selecting_price=None,
        selected_modifiers=[]
    )

    cart = [CartItem(**c) for c in data.get("cart", [])]
    menu = await db.get_menu()
    favorite_ids = await db.get_user_favorite_ids(callback.from_user.id)

    await msg.edit_text(
        "Выбери напитки из меню:",
        reply_markup=menu_keyboard(menu, cart, favorite_ids)
    )
    await callback.answer()


# ===== CART =====

@router.callback_query(F.data == "cart:show", OrderState.browsing_menu)
async def show_cart(callback: CallbackQuery, state: FSMContext) -> None:
    msg = _get_editable_message(callback)
    if not msg:
        await callback.answer("Сообщение недоступно")
        return

    data = await state.get_data()
    cart = [CartItem(**c) for c in data.get("cart", [])]

    if not cart:
        logger.warning(
            "empty_cart",
            extra={"user_id": callback.from_user.id, "action": "show_cart"}
        )
        await callback.answer("Корзина пуста")
        return

    text = _format_cart_text(cart)
    await msg.edit_text(text, reply_markup=cart_keyboard(cart), parse_mode="HTML")


@router.callback_query(F.data == "cart:back", OrderState.browsing_menu)
async def cart_back_to_menu(callback: CallbackQuery, state: FSMContext) -> None:
    msg = _get_editable_message(callback)
    if not msg:
        await callback.answer("Сообщение недоступно")
        return

    data = await state.get_data()
    cart = [CartItem(**c) for c in data.get("cart", [])]
    menu = await db.get_menu()
    favorite_ids = await db.get_user_favorite_ids(callback.from_user.id)

    await msg.edit_text(
        "Выбери напитки из меню:",
        reply_markup=menu_keyboard(menu, cart, favorite_ids)
    )


def _format_cart_text(cart: list[CartItem]) -> str:
    """Форматирует текст корзины с модификаторами"""
    text = "Корзина:\n\n"
    total = 0
    for item in cart:
        line_total = item.price * item.quantity
        total += line_total
        size_suffix = f" ({item.size})" if item.size else ""
        text += f"* {item.name}{size_suffix} x{item.quantity} = {line_total}\u20bd\n"
        # Показываем модификаторы
        if item.modifier_names:
            mods_str = ", ".join(item.modifier_names)
            text += f"  + {mods_str}\n"
        if item.comment:
            text += f"  {html.escape(item.comment)}\n"
    text += f"\nИтого: {total}\u20bd"
    return text


def _parse_cart_key(cart_key: str) -> tuple[int, str | None, list[int]]:
    """
    Парсит ключ корзины: "123:none:none" -> (123, None, [])
    "123:M:1-2-3" -> (123, "M", [1, 2, 3])
    """
    parts = cart_key.split(":")
    item_id = int(parts[0])

    size = parts[1] if len(parts) > 1 and parts[1] != "none" else None

    modifier_ids: list[int] = []
    if len(parts) > 2 and parts[2] != "none":
        modifier_ids = [int(mid) for mid in parts[2].split("-")]

    return item_id, size, modifier_ids


def _cart_item_matches(cart_item: dict[str, Any], item_id: int, size: str | None, modifier_ids: list[int]) -> bool:
    """Проверяет соответствие позиции корзины ключу"""
    if cart_item["menu_item_id"] != item_id:
        return False
    if cart_item.get("size") != size:
        return False
    # Сравниваем модификаторы (отсортированные)
    item_mods = sorted(cart_item.get("modifier_ids", []))
    return item_mods == sorted(modifier_ids)


@router.callback_query(F.data.startswith("cart:inc:"), OrderState.browsing_menu)
async def cart_increase(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.data:
        await callback.answer()
        return

    cart_key = callback.data.split(":", 2)[2]
    item_id, size, modifier_ids = _parse_cart_key(cart_key)

    data = await state.get_data()
    cart = data.get("cart", [])

    for c in cart:
        if _cart_item_matches(c, item_id, size, modifier_ids):
            c["quantity"] += 1
            break

    await state.update_data(cart=cart)
    await _update_cart_view(callback, cart)


@router.callback_query(F.data.startswith("cart:dec:"), OrderState.browsing_menu)
async def cart_decrease(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.data:
        await callback.answer()
        return
    msg = _get_editable_message(callback)
    if not msg:
        await callback.answer("Сообщение недоступно")
        return

    cart_key = callback.data.split(":", 2)[2]
    item_id, size, modifier_ids = _parse_cart_key(cart_key)

    data = await state.get_data()
    cart = data.get("cart", [])

    new_cart = []
    for c in cart:
        if _cart_item_matches(c, item_id, size, modifier_ids):
            if c["quantity"] > 1:
                c["quantity"] -= 1
                new_cart.append(c)
        else:
            new_cart.append(c)

    await state.update_data(cart=new_cart)

    if new_cart:
        await _update_cart_view(callback, new_cart)
    else:
        menu = await db.get_menu()
        favorite_ids = await db.get_user_favorite_ids(callback.from_user.id)
        await msg.edit_text(
            "Выбери напитки из меню:",
            reply_markup=menu_keyboard(menu, [], favorite_ids)
        )


async def _update_cart_view(callback: CallbackQuery, cart_data: list[dict[str, Any]]) -> None:
    msg = _get_editable_message(callback)
    if not msg:
        await callback.answer("Сообщение недоступно")
        return
    cart = [CartItem(**c) for c in cart_data]
    text = _format_cart_text(cart)
    await msg.edit_text(text, reply_markup=cart_keyboard(cart), parse_mode="HTML")


# ===== COMMENTS =====

MAX_COMMENT_LENGTH = 100


@router.callback_query(F.data.startswith("cart:comment:"), OrderState.browsing_menu)
async def start_comment(callback: CallbackQuery, state: FSMContext) -> None:
    """Начинает ввод комментария к позиции"""
    if not callback.data:
        await callback.answer()
        return
    msg = _get_editable_message(callback)
    if not msg:
        await callback.answer("Сообщение недоступно")
        return

    cart_key = callback.data.split(":", 2)[2]
    item_id, size, modifier_ids = _parse_cart_key(cart_key)

    data = await state.get_data()
    cart = data.get("cart", [])

    item_name = None
    current_comment = None
    for c in cart:
        if _cart_item_matches(c, item_id, size, modifier_ids):
            item_name = c["name"]
            if c.get("size"):
                item_name += f" ({c['size']})"
            current_comment = c.get("comment")
            break

    if not item_name:
        await callback.answer("Позиция не найдена")
        return

    await state.update_data(commenting_cart_key=cart_key)
    await state.set_state(OrderState.entering_comment)

    text = f"Введи комментарий к <b>{html.escape(item_name)}</b>\n"
    text += "(например: без сахара, с корицей)\n\n"
    if current_comment:
        text += f"Текущий: {html.escape(current_comment)}\n\n"
    text += "Отправь /cancel чтобы отменить"

    await msg.edit_text(text, parse_mode="HTML")

    logger.debug(
        "comment_started",
        extra={"user_id": callback.from_user.id, "cart_key": cart_key, "item_name": item_name}
    )


@router.message(Command("cancel"), OrderState.entering_comment)
async def cancel_comment(message: Message, state: FSMContext) -> None:
    """Отменяет ввод комментария"""
    await state.set_state(OrderState.browsing_menu)
    await state.update_data(commenting_cart_key=None)

    data = await state.get_data()
    cart = [CartItem(**c) for c in data.get("cart", [])]
    text = _format_cart_text(cart)
    await message.answer(text, reply_markup=cart_keyboard(cart), parse_mode="HTML")


@router.message(OrderState.entering_comment)
async def save_comment(message: Message, state: FSMContext) -> None:
    """Сохраняет комментарий к позиции"""
    if not message.from_user or not message.text:
        return

    comment = message.text.strip()

    if len(comment) > MAX_COMMENT_LENGTH:
        await message.answer(
            f"Комментарий слишком длинный (макс. {MAX_COMMENT_LENGTH} символов).\n"
            "Попробуй короче или /cancel для отмены"
        )
        return

    data = await state.get_data()
    cart_key = data.get("commenting_cart_key")
    cart = data.get("cart", [])

    if not cart_key:
        await state.set_state(OrderState.browsing_menu)
        await message.answer("Позиция не найдена. Попробуй снова.")
        return

    item_id, size, modifier_ids = _parse_cart_key(cart_key)

    item_name = None
    for c in cart:
        if _cart_item_matches(c, item_id, size, modifier_ids):
            c["comment"] = comment
            item_name = c["name"]
            if c.get("size"):
                item_name += f" ({c['size']})"
            break

    if not item_name:
        await state.set_state(OrderState.browsing_menu)
        await message.answer("Позиция не найдена. Попробуй снова.")
        return

    await state.update_data(cart=cart, commenting_cart_key=None)
    await state.set_state(OrderState.browsing_menu)

    logger.info(
        "comment_saved",
        extra={
            "user_id": message.from_user.id,
            "cart_key": cart_key,
            "item_name": item_name,
            "comment_length": len(comment)
        }
    )

    cart_items = [CartItem(**c) for c in cart]
    text = _format_cart_text(cart_items)
    await message.answer(text, reply_markup=cart_keyboard(cart_items), parse_mode="HTML")


def _format_order_summary(items: list[OrderItem]) -> str:
    """Краткий summary состава заказа для уведомлений"""
    if len(items) == 1:
        item = items[0]
        size_suffix = f" ({item.size})" if item.size else ""
        qty_str = f" x{item.quantity}" if item.quantity > 1 else ""
        return f"{item.name}{size_suffix}{qty_str}"

    # Несколько позиций: первые 3
    parts = []
    for item in items[:3]:
        size_suffix = f" ({item.size})" if item.size else ""
        parts.append(f"{item.name}{size_suffix} x{item.quantity}")

    result = ", ".join(parts)
    if len(items) > 3:
        result += f" и ещё {len(items) - 3}"
    return result


async def _notify_baristas(bot: Bot, order: Order, items: list[OrderItem]) -> None:
    """
    Уведомляет всех баристов о новом заказе.
    Не блокирует создание заказа при ошибках.
    """
    barista_ids = settings.barista_id_list

    if not barista_ids:
        logger.info(
            "no_baristas_configured",
            extra={"order_id": order.id, "user_id": order.user_id}
        )
        return

    summary = _format_order_summary(items)
    message = (
        f"🔔 Новый заказ #{order.id}\n\n"
        f"👤 Клиент: {order.user_name}\n"
        f"📦 Состав: {summary}\n"
        f"💰 Сумма: {order.total}р\n"
        f"⏰ Забор: {order.pickup_time}\n\n"
        f"/barista — открыть панель"
    )

    async def send_to_barista(barista_id: int) -> tuple[int, bool, str | None]:
        """Возвращает (barista_id, success, error_message)"""
        try:
            await bot.send_message(barista_id, message)
            logger.info(
                "barista_notified",
                extra={
                    "order_id": order.id,
                    "barista_id": barista_id,
                    "user_id": order.user_id
                }
            )
            return (barista_id, True, None)
        except Exception as e:
            logger.error(
                "barista_notification_failed",
                extra={
                    "order_id": order.id,
                    "barista_id": barista_id,
                    "user_id": order.user_id,
                    "error": str(e)
                },
                exc_info=True
            )
            return (barista_id, False, str(e))

    results = await asyncio.gather(
        *[send_to_barista(bid) for bid in barista_ids],
        return_exceptions=False
    )

    success_count = sum(1 for _, success, _ in results if success)
    fail_count = len(results) - success_count

    logger.info(
        "baristas_notified",
        extra={
            "order_id": order.id,
            "user_id": order.user_id,
            "success_count": success_count,
            "fail_count": fail_count,
            "total_count": len(barista_ids)
        }
    )


# ===== CHECKOUT =====

@router.callback_query(F.data == "cart:checkout", OrderState.browsing_menu)
async def checkout(callback: CallbackQuery, state: FSMContext) -> None:
    msg = _get_editable_message(callback)
    if not msg:
        await callback.answer("Сообщение недоступно")
        return

    data = await state.get_data()
    cart = data.get("cart", [])

    if not cart:
        await callback.answer("Корзина пуста")
        return

    logger.debug(
        "fsm_transition",
        extra={
            "user_id": callback.from_user.id,
            "from_state": "browsing_menu",
            "to_state": "selecting_time",
            "cart_size": len(cart),
            "total": sum(c["price"] * c["quantity"] for c in cart)
        }
    )

    await state.set_state(OrderState.selecting_time)
    await msg.edit_text(
        "Когда заберёшь заказ?",
        reply_markup=pickup_time_keyboard()
    )


# ===== TIME SELECTION =====

@router.callback_query(F.data == "time:back", OrderState.selecting_time)
async def time_back(callback: CallbackQuery, state: FSMContext) -> None:
    msg = _get_editable_message(callback)
    if not msg:
        await callback.answer("Сообщение недоступно")
        return

    await state.set_state(OrderState.browsing_menu)
    data = await state.get_data()
    cart = [CartItem(**c) for c in data.get("cart", [])]
    await msg.edit_text("Корзина:", reply_markup=cart_keyboard(cart))


@router.callback_query(F.data.startswith("time:"), OrderState.selecting_time)
async def select_time(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.data:
        await callback.answer()
        return

    minutes = callback.data.split(":")[1]
    if minutes == "back":
        return

    pickup_time = f"через {minutes} мин"
    await state.update_data(pickup_time=pickup_time)

    # Проверяем баллы пользователя
    loyalty_data = await loyalty.get_or_create_loyalty(callback.from_user.id)
    user_points = loyalty_data["points"]

    data = await state.get_data()
    cart = data.get("cart", [])
    order_total = sum(c["price"] * c["quantity"] for c in cart)

    if user_points > 0:
        max_redeem = loyalty.calculate_max_redeem(order_total, user_points)

        if max_redeem > 0:
            msg = _get_editable_message(callback)
            if not msg:
                await callback.answer("Сообщение недоступно")
                return

            await state.set_state(OrderState.applying_bonus)
            await msg.edit_text(
                f"У тебя {user_points} баллов\n\n"
                f"Хочешь списать баллы?\n"
                f"(1 балл = 1р скидки, макс. 30% от суммы)",
                reply_markup=bonus_keyboard(user_points, max_redeem, order_total)
            )
            return

    await state.update_data(bonus_used=0)
    await _show_confirmation(callback, state)


async def _show_confirmation(callback: CallbackQuery, state: FSMContext) -> None:
    """Показывает экран подтверждения заказа с учётом бонусов"""
    msg = _get_editable_message(callback)
    if not msg:
        await callback.answer("Сообщение недоступно")
        return

    await state.set_state(OrderState.confirming)
    data = await state.get_data()
    cart = [CartItem(**c) for c in data.get("cart", [])]
    pickup_time = data.get("pickup_time", "через 15 мин")
    bonus_used = data.get("bonus_used", 0)

    text = "Проверь заказ:\n\n"
    total = 0
    for item in cart:
        line_total = item.price * item.quantity
        total += line_total
        size_suffix = f" ({item.size})" if item.size else ""
        text += f"* {item.name}{size_suffix} x{item.quantity} = {line_total}р\n"
        if item.modifier_names:
            mods_str = ", ".join(item.modifier_names)
            text += f"  + {mods_str}\n"

    text += f"\nСумма: {total}р"

    if bonus_used > 0:
        final_total = total - bonus_used
        text += f"\nСкидка баллами: -{bonus_used}р"
        text += f"\nИтого к оплате: {final_total}р"
    else:
        text += f"\nИтого: {total}р"

    text += f"\nЗабор: {pickup_time}"

    await msg.edit_text(text, reply_markup=confirm_keyboard())


# ===== BONUS =====

@router.callback_query(F.data == "bonus:skip", OrderState.applying_bonus)
async def bonus_skip(callback: CallbackQuery, state: FSMContext) -> None:
    """Пользователь пропускает списание баллов"""
    await state.update_data(bonus_used=0)
    logger.debug(
        "bonus_skipped",
        extra={"user_id": callback.from_user.id}
    )
    await _show_confirmation(callback, state)


@router.callback_query(F.data.startswith("bonus:use:"), OrderState.applying_bonus)
async def bonus_use(callback: CallbackQuery, state: FSMContext) -> None:
    """Пользователь выбрал фиксированную сумму баллов"""
    if not callback.data:
        await callback.answer()
        return
    amount = int(callback.data.split(":")[2])
    await state.update_data(bonus_used=amount)
    logger.debug(
        "bonus_selected",
        extra={"user_id": callback.from_user.id, "amount": amount}
    )
    await _show_confirmation(callback, state)


@router.callback_query(F.data == "bonus:max", OrderState.applying_bonus)
async def bonus_max(callback: CallbackQuery, state: FSMContext) -> None:
    """Пользователь выбрал максимальное списание"""
    data = await state.get_data()
    cart = data.get("cart", [])
    order_total = sum(c["price"] * c["quantity"] for c in cart)

    loyalty_data = await loyalty.get_or_create_loyalty(callback.from_user.id)
    user_points = loyalty_data["points"]
    max_redeem = loyalty.calculate_max_redeem(order_total, user_points)

    await state.update_data(bonus_used=max_redeem)
    logger.debug(
        "bonus_max_selected",
        extra={"user_id": callback.from_user.id, "amount": max_redeem}
    )
    await _show_confirmation(callback, state)


# ===== CONFIRM =====

@router.callback_query(F.data == "confirm:edit", OrderState.confirming)
async def confirm_edit(callback: CallbackQuery, state: FSMContext) -> None:
    msg = _get_editable_message(callback)
    if not msg:
        await callback.answer("Сообщение недоступно")
        return

    await state.set_state(OrderState.browsing_menu)
    data = await state.get_data()
    cart = [CartItem(**c) for c in data.get("cart", [])]
    await msg.edit_text("Корзина:", reply_markup=cart_keyboard(cart))


@router.callback_query(F.data == "confirm:yes", OrderState.confirming)
async def confirm_order(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    msg = _get_editable_message(callback)
    if not msg:
        await callback.answer("Сообщение недоступно")
        return

    data = await state.get_data()
    cart_data = data.get("cart", [])
    pickup_time = data.get("pickup_time", "через 15 мин")
    bonus_used = data.get("bonus_used", 0)

    if not cart_data:
        await callback.answer("Корзина пуста")
        return

    user = callback.from_user
    user_name = user.full_name or user.username or f"user_{user.id}"

    items = [
        OrderItem(
            menu_item_id=c["menu_item_id"],
            name=c["name"],
            price=c["price"],
            quantity=c["quantity"],
            comment=c.get("comment"),
            size=c.get("size"),
            size_name=c.get("size_name"),
            modifier_ids=c.get("modifier_ids", []),
            modifier_names=c.get("modifier_names", []),
            modifiers_price=c.get("modifiers_price", 0),
        )
        for c in cart_data
    ]

    order = await db.create_order(
        user_id=user.id,
        user_name=user_name,
        items=items,
        pickup_time=pickup_time
    )

    # Списываем баллы если использовались
    if bonus_used > 0:
        redeem_success = await loyalty.redeem_points(user.id, bonus_used, order.id)
        if redeem_success:
            logger.info(
                "bonus_redeemed",
                extra={
                    "user_id": user.id,
                    "order_id": order.id,
                    "bonus_used": bonus_used
                }
            )
        else:
            logger.warning(
                "bonus_redeem_failed",
                extra={
                    "user_id": user.id,
                    "order_id": order.id,
                    "bonus_used": bonus_used
                }
            )
            bonus_used = 0  # сбрасываем если не удалось списать

    # Сумма для начисления баллов — полная (до скидки)
    order_total = order.total
    final_total = order_total - bonus_used

    logger.info(
        "order_created",
        extra={
            "user_id": user.id,
            "order_id": order.id,
            "total": order_total,
            "bonus_used": bonus_used,
            "final_total": final_total,
            "items_count": len(items),
            "pickup_time": pickup_time
        }
    )

    # Начисляем баллы за заказ (от полной суммы)
    points_earned = await loyalty.accrue_points(user.id, order_total, order.id)

    # Увеличиваем штампы
    new_stamps, free_drink = await loyalty.increment_stamps(user.id)

    logger.info(
        "loyalty_accrued",
        extra={
            "user_id": user.id,
            "order_id": order.id,
            "points_earned": points_earned,
            "new_stamps": new_stamps,
            "free_drink": free_drink
        }
    )

    # Уведомляем баристов о новом заказе
    await _notify_baristas(bot, order, items)

    await state.clear()

    # Формируем сообщение подтверждения
    if bonus_used > 0:
        sum_line = f"Сумма: {order_total}р\nСкидка баллами: -{bonus_used}р\nК оплате: {final_total}р"
    else:
        sum_line = f"Сумма: {order_total}р"

    stamps_bar = _stamps_progress_bar(new_stamps, loyalty.STAMPS_FOR_FREE_DRINK)

    if free_drink:
        confirmation_text = (
            f"Заказ #{order.id} оформлен!\n\n"
            f"Время забора: {pickup_time}\n"
            f"{sum_line}\n\n"
            f"+{points_earned} баллов начислено\n"
            f"Штампов: {stamps_bar} {new_stamps}/{loyalty.STAMPS_FOR_FREE_DRINK}\n"
            f"Поздравляем! Следующий напиток бесплатно!\n\n"
            "Мы напишем, когда будет готово.\n"
            "/start — новый заказ"
        )
    else:
        confirmation_text = (
            f"Заказ #{order.id} оформлен!\n\n"
            f"Время забора: {pickup_time}\n"
            f"{sum_line}\n\n"
            f"+{points_earned} баллов начислено\n"
            f"Штампов: {stamps_bar} {new_stamps}/{loyalty.STAMPS_FOR_FREE_DRINK}\n\n"
            "Мы напишем, когда будет готово.\n"
            "/start — новый заказ"
        )

    await msg.edit_text(confirmation_text)


# ===== HISTORY =====

HISTORY_PAGE_SIZE = 5


def _status_emoji(status: OrderStatus) -> str:
    return {
        OrderStatus.PENDING: "⏳",
        OrderStatus.CONFIRMED: "📋",
        OrderStatus.PREPARING: "🔄",
        OrderStatus.READY: "✅",
        OrderStatus.COMPLETED: "✅",
        OrderStatus.CANCELLED: "❌",
    }.get(status, "")


def _format_history_list(orders: list[Order], page: int, total_pages: int) -> str:
    if not orders:
        return "У вас пока нет заказов.\n\nДля оформления: /start"

    text = f"История заказов (стр. {page + 1}/{total_pages}):\n\n"
    for order in orders:
        items_summary = ", ".join(
            f"{item.name}" + (f" ({item.size})" if item.size else "") + (f" x{item.quantity}" if item.quantity > 1 else "")
            for item in order.items[:2]
        )
        if len(order.items) > 2:
            items_summary += "..."

        emoji = _status_emoji(order.status)
        text += f"#{order.id} — {items_summary} — {order.total}р — {emoji} {order.status.display_name}\n"

    return text


def _format_order_detail(order: Order) -> str:
    date_str = order.created_at.strftime("%d.%m.%Y")
    text = f"Заказ #{order.id} от {date_str}\n\n"
    text += "Состав:\n"
    for item in order.items:
        line_total = item.price * item.quantity
        size_suffix = f" ({item.size})" if item.size else ""
        text += f"• {item.name}{size_suffix} x{item.quantity} = {line_total}р\n"

    emoji = _status_emoji(order.status)
    text += f"\nИтого: {order.total}р\n"
    text += f"Статус: {emoji} {order.status.display_name}\n"
    text += f"Забор: {order.pickup_time}"

    return text


@router.message(Command("history"))
async def cmd_history(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    user_id = message.from_user.id
    orders, total = await db.get_user_orders(user_id, limit=HISTORY_PAGE_SIZE, offset=0)

    logger.debug(
        "history_view",
        extra={"user_id": user_id, "total_orders": total, "page": 0}
    )

    total_pages = max(1, (total + HISTORY_PAGE_SIZE - 1) // HISTORY_PAGE_SIZE)
    has_next = total > HISTORY_PAGE_SIZE

    text = _format_history_list(orders, page=0, total_pages=total_pages)

    if orders:
        await state.update_data(history_page=0)
        await message.answer(text, reply_markup=history_keyboard(orders, page=0, has_next=has_next))
    else:
        await message.answer(text)


@router.callback_query(F.data.startswith("history:page:"))
async def history_page(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.data:
        await callback.answer()
        return
    msg = _get_editable_message(callback)
    if not msg:
        await callback.answer("Сообщение недоступно")
        return

    page = int(callback.data.split(":")[2])
    user_id = callback.from_user.id
    offset = page * HISTORY_PAGE_SIZE

    orders, total = await db.get_user_orders(user_id, limit=HISTORY_PAGE_SIZE, offset=offset)

    logger.debug(
        "history_page",
        extra={"user_id": user_id, "page": page, "total": total}
    )

    total_pages = max(1, (total + HISTORY_PAGE_SIZE - 1) // HISTORY_PAGE_SIZE)
    has_next = offset + HISTORY_PAGE_SIZE < total

    text = _format_history_list(orders, page=page, total_pages=total_pages)

    await state.update_data(history_page=page)
    await msg.edit_text(text, reply_markup=history_keyboard(orders, page=page, has_next=has_next))


@router.callback_query(F.data.startswith("history:view:"))
async def history_view_order(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.data:
        await callback.answer()
        return
    msg = _get_editable_message(callback)
    if not msg:
        await callback.answer("Сообщение недоступно")
        return

    order_id = int(callback.data.split(":")[2])
    order = await db.get_order(order_id)

    if not order:
        logger.warning(
            "history_order_not_found",
            extra={"user_id": callback.from_user.id, "order_id": order_id}
        )
        await callback.answer("Заказ не найден")
        return

    if order.user_id != callback.from_user.id:
        logger.warning(
            "history_order_access_denied",
            extra={"user_id": callback.from_user.id, "order_id": order_id, "owner_id": order.user_id}
        )
        await callback.answer("Нет доступа к заказу")
        return

    logger.debug(
        "history_view_detail",
        extra={"user_id": callback.from_user.id, "order_id": order_id}
    )

    text = _format_order_detail(order)
    await msg.edit_text(
        text,
        reply_markup=order_detail_keyboard(order_id, order=order, user_id=callback.from_user.id)
    )


@router.callback_query(F.data == "history:back")
async def history_back(callback: CallbackQuery, state: FSMContext) -> None:
    msg = _get_editable_message(callback)
    if not msg:
        await callback.answer("Сообщение недоступно")
        return

    data = await state.get_data()
    page = data.get("history_page", 0)
    user_id = callback.from_user.id
    offset = page * HISTORY_PAGE_SIZE

    orders, total = await db.get_user_orders(user_id, limit=HISTORY_PAGE_SIZE, offset=offset)

    logger.debug(
        "history_back",
        extra={"user_id": user_id, "page": page}
    )

    total_pages = max(1, (total + HISTORY_PAGE_SIZE - 1) // HISTORY_PAGE_SIZE)
    has_next = offset + HISTORY_PAGE_SIZE < total

    text = _format_history_list(orders, page=page, total_pages=total_pages)
    await msg.edit_text(text, reply_markup=history_keyboard(orders, page=page, has_next=has_next))


# ===== ORDER CANCELLATION =====

@router.callback_query(F.data.startswith("cancel:"))
async def cancel_order(callback: CallbackQuery, bot: Bot) -> None:
    """Отмена заказа клиентом"""
    if not callback.data:
        await callback.answer()
        return
    msg = _get_editable_message(callback)
    if not msg:
        await callback.answer("Сообщение недоступно")
        return

    order_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    order = await db.get_order(order_id)

    success, message = await db.cancel_order_by_client(order_id, user_id)

    if success:
        refunded_points = await loyalty.refund_points(user_id, order_id)

        if refunded_points > 0:
            logger.info(
                "points_refunded",
                extra={
                    "user_id": user_id,
                    "order_id": order_id,
                    "refunded_points": refunded_points
                }
            )

        await callback.answer(message)

        if order:
            await _notify_baristas_cancellation(bot, order, refunded_points)

        updated_order = await db.get_order(order_id)
        if updated_order:
            text = f"❌ Заказ #{order_id} отменён"

            if refunded_points > 0:
                text += f"\n\n💰 Возвращено {refunded_points} баллов"

            text += "\n\nЕсли хотите сделать новый заказ — /start"

            await msg.edit_text(text)
    else:
        await callback.answer(message, show_alert=True)


async def _notify_baristas_cancellation(bot: Bot, order: Order, refunded_points: int = 0) -> None:
    """Уведомляет баристов об отмене заказа клиентом"""
    barista_ids = settings.barista_id_list

    if not barista_ids:
        return

    # Форматируем состав заказа
    items_text = ""
    for item in order.items:
        size_suffix = f" ({item.size})" if item.size else ""
        items_text += f"• {item.name}{size_suffix} x{item.quantity} — {item.price * item.quantity}₽\n"
        if item.modifier_names:
            mods_str = ", ".join(item.modifier_names)
            items_text += f"  + {mods_str}\n"

    message = (
        f"❌ Заказ #{order.id} отменён клиентом\n\n"
        f"Был:\n{items_text}"
    )

    if refunded_points > 0:
        message += f"\n💰 Клиенту возвращено {refunded_points} баллов"

    for barista_id in barista_ids:
        try:
            await bot.send_message(barista_id, message)
            logger.info(
                "barista_notified_cancellation",
                extra={"order_id": order.id, "barista_id": barista_id}
            )
        except Exception as e:
            logger.error(
                "barista_cancellation_notification_failed",
                extra={"order_id": order.id, "barista_id": barista_id, "error": str(e)},
                exc_info=True
            )


# ===== REPEAT ORDER =====

@router.callback_query(F.data.startswith("repeat:"))
async def repeat_order(callback: CallbackQuery, state: FSMContext) -> None:
    """Повторить заказ — добавить позиции в корзину."""
    if not callback.data:
        await callback.answer()
        return
    msg = _get_editable_message(callback)
    if not msg:
        await callback.answer("Сообщение недоступно")
        return

    order_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    order = await db.get_order(order_id)
    if not order or order.user_id != user_id:
        logger.warning(
            "repeat_order_access_denied",
            extra={"user_id": user_id, "order_id": order_id}
        )
        await callback.answer("Заказ не найден")
        return

    items_for_repeat = await db.get_order_items_for_repeat(order_id)

    if not items_for_repeat:
        await callback.answer("Не удалось загрузить заказ")
        return

    available_items = [i for i in items_for_repeat if i["is_available"]]
    unavailable_items = [i for i in items_for_repeat if not i["is_available"]]

    if not available_items:
        logger.info(
            "repeat_order_all_unavailable",
            extra={"user_id": user_id, "order_id": order_id, "count": len(unavailable_items)}
        )
        unavailable_names = [i["name"] for i in unavailable_items]
        text = "К сожалению, все позиции из этого заказа сейчас недоступны:\n"
        for name in unavailable_names:
            text += f"• {name} (нет в наличии)\n"
        text += "\n/start - новый заказ\n/history - история заказов"

        await callback.answer("Все позиции недоступны", show_alert=True)
        await msg.edit_text(text)
        return

    current_state = await state.get_state()
    if current_state != OrderState.browsing_menu:
        await state.set_state(OrderState.browsing_menu)
        await state.update_data(cart=[])

    data = await state.get_data()
    cart: list[dict[str, Any]] = data.get("cart", [])

    # 2. Добавить доступные в корзину (с модификаторами)
    added_names: list[str] = []
    for item in available_items:
        # Ищем совпадение: menu_item_id + size + modifier_ids
        found = False
        sorted_mods = sorted(item.get("modifier_ids", []))

        for c in cart:
            if (c["menu_item_id"] == item["menu_item_id"]
                    and c.get("size") == item.get("size")
                    and sorted(c.get("modifier_ids", [])) == sorted_mods):
                c["quantity"] += item["quantity"]
                found = True
                break

        if not found:
            cart.append({
                "menu_item_id": item["menu_item_id"],
                "name": item["name"],
                "price": item["price"],
                "quantity": item["quantity"],
                "size": item.get("size"),
                "size_name": item.get("size_name"),
                "modifier_ids": item.get("modifier_ids", []),
                "modifier_names": item.get("modifier_names", []),
                "modifiers_price": item.get("modifiers_price", 0),
            })

        size_suffix = f" ({item.get('size')})" if item.get("size") else ""
        qty_str = f" x{item['quantity']}" if item["quantity"] > 1 else ""
        added_names.append(f"• {item['name']}{size_suffix}{qty_str}")

    await state.update_data(cart=cart)

    logger.info(
        "repeat_order_success",
        extra={
            "user_id": user_id,
            "order_id": order_id,
            "added_count": len(available_items),
            "unavailable_count": len(unavailable_items)
        }
    )

    # 3/4. Формируем сообщение с предупреждением о недоступных
    if unavailable_items:
        unavailable_names = [i["name"] for i in unavailable_items]
        text = "⚠️ Некоторые позиции недоступны:\n"
        for name in unavailable_names:
            text += f"• {name} (нет в наличии)\n"
        text += "\n✅ Добавлено в корзину:\n"
        text += "\n".join(added_names)
    else:
        text = "✅ Добавлено в корзину:\n"
        text += "\n".join(added_names)

    cart_items = [CartItem(**c) for c in cart]
    text += f"\n\n{_format_cart_text(cart_items)}"

    await msg.edit_text(
        text,
        reply_markup=cart_keyboard(cart_items),
        parse_mode="HTML"
    )


# ===== FAVORITES =====

@router.message(Command("favorites"))
async def cmd_favorites(message: Message) -> None:
    """Показывает список избранных позиций"""
    if not message.from_user:
        return
    user_id = message.from_user.id
    favorites = await db.get_favorites(user_id)

    logger.debug(
        "favorites_view",
        extra={"user_id": user_id, "count": len(favorites)}
    )

    if not favorites:
        await message.answer(
            "Избранное пусто.\n\n"
            "Добавляйте позиции в избранное через меню.\n"
            "Для нового заказа: /start"
        )
        return

    text = "Избранное:\n\n"
    for item in favorites:
        text += f"* {item.name} — {item.price}р\n"
    text += "\nДля нового заказа: /start"

    await message.answer(text, reply_markup=favorites_keyboard(favorites))


@router.callback_query(F.data.startswith("fav:add:"))
async def fav_add(callback: CallbackQuery) -> None:
    """Добавляет позицию в избранное"""
    if not callback.data:
        await callback.answer()
        return

    item_id = int(callback.data.split(":")[2])
    user_id = callback.from_user.id

    item = await db.get_menu_item(item_id)
    if not item:
        logger.warning(
            "fav_add_item_not_found",
            extra={"user_id": user_id, "item_id": item_id}
        )
        await callback.answer("Позиция не найдена")
        return

    added = await db.add_favorite(user_id, item_id)

    if added:
        logger.info(
            "favorite_added",
            extra={"user_id": user_id, "item_id": item_id, "item_name": item.name}
        )
        await callback.answer(f"* {item.name} добавлен в избранное")
    else:
        await callback.answer("Уже в избранном")


@router.callback_query(F.data.startswith("fav:remove:"))
async def fav_remove(callback: CallbackQuery) -> None:
    """Удаляет позицию из избранного"""
    if not callback.data:
        await callback.answer()
        return
    msg = _get_editable_message(callback)
    if not msg:
        await callback.answer("Сообщение недоступно")
        return

    item_id = int(callback.data.split(":")[2])
    user_id = callback.from_user.id

    item = await db.get_menu_item(item_id)
    item_name = item.name if item else f"#{item_id}"

    removed = await db.remove_favorite(user_id, item_id)

    if removed:
        logger.info(
            "favorite_removed",
            extra={"user_id": user_id, "item_id": item_id}
        )
        await callback.answer(f"{item_name} убран из избранного")

        favorites = await db.get_favorites(user_id)
        if favorites:
            text = "Избранное:\n\n"
            for fav in favorites:
                text += f"* {fav.name} — {fav.price}р\n"
            text += "\nДля нового заказа: /start"
            await msg.edit_text(text, reply_markup=favorites_keyboard(favorites))
        else:
            await msg.edit_text(
                "Избранное пусто.\n\n"
                "Добавляйте позиции в избранное через меню.\n"
                "Для нового заказа: /start"
            )
    else:
        await callback.answer("Позиция не была в избранном")


@router.callback_query(F.data.startswith("fav:order:"))
async def fav_order(callback: CallbackQuery, state: FSMContext) -> None:
    """Добавляет позицию из избранного в корзину"""
    if not callback.data:
        await callback.answer()
        return

    item_id = int(callback.data.split(":")[2])
    user_id = callback.from_user.id

    item = await db.get_menu_item(item_id)
    if not item or not item.available:
        logger.warning(
            "fav_order_item_unavailable",
            extra={"user_id": user_id, "item_id": item_id}
        )
        await callback.answer("Позиция недоступна")
        return

    current_state = await state.get_state()
    if current_state != OrderState.browsing_menu:
        await state.set_state(OrderState.browsing_menu)
        await state.update_data(cart=[])

    data = await state.get_data()
    cart: list[dict[str, Any]] = data.get("cart", [])

    found = False
    for c in cart:
        if c["menu_item_id"] == item_id:
            c["quantity"] += 1
            found = True
            break

    if not found:
        cart.append({
            "menu_item_id": item.id,
            "name": item.name,
            "price": item.price,
            "quantity": 1
        })

    await state.update_data(cart=cart)

    logger.debug(
        "fav_order_added",
        extra={"user_id": user_id, "item_id": item_id, "item_name": item.name}
    )

    await callback.answer(f"{item.name} добавлен в корзину")


@router.callback_query(F.data == "fav:start")
async def fav_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Переход в меню из избранного"""
    msg = _get_editable_message(callback)
    if not msg:
        await callback.answer("Сообщение недоступно")
        return

    await state.clear()
    await state.set_state(OrderState.browsing_menu)
    await state.update_data(cart=[])

    menu = await db.get_menu()
    favorite_ids = await db.get_user_favorite_ids(callback.from_user.id)

    await msg.edit_text(
        "Выбери напитки из меню:",
        reply_markup=menu_keyboard(menu, [], favorite_ids)
    )


# ===== PROFILE =====

def _stamps_progress_bar(stamps: int, max_stamps: int = 6) -> str:
    """Генерация прогресс-бара штампов."""
    filled = "●" * min(stamps, max_stamps)
    empty = "○" * (max_stamps - min(stamps, max_stamps))
    return f"[{filled}{empty}]"


def _format_money(value: int) -> str:
    """Форматирует сумму с разделителями: 4500 -> 4 500"""
    return f"{value:,}".replace(",", " ")


@router.message(Command("profile"))
async def cmd_profile(message: Message) -> None:
    """Показать профиль пользователя."""
    if not message.from_user:
        return
    user_id = message.from_user.id

    data = await loyalty.get_or_create_loyalty(user_id)

    points = data["points"]
    stamps = data["stamps"]
    total_orders = data["total_orders"]
    total_spent = data["total_spent"]

    max_stamps = loyalty.STAMPS_FOR_FREE_DRINK
    progress_bar = _stamps_progress_bar(stamps, max_stamps)

    text = (
        f"👤 Ваш профиль\n\n"
        f"💰 Баллы: {points}\n"
        f"🎫 Штампы: {stamps}/{max_stamps} {progress_bar}\n\n"
        f"📊 Статистика:\n"
        f"• Заказов: {total_orders}\n"
        f"• Потрачено: {_format_money(total_spent)}₽\n\n"
        f"ℹ️ 5 баллов за каждые 100₽\n"
        f"ℹ️ {max_stamps} штампов = бесплатный напиток"
    )

    await message.answer(text)
