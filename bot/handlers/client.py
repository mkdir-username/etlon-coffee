from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot import database as db
from bot.models import CartItem, OrderItem
from bot.states import OrderState
from bot.keyboards import (
    menu_keyboard,
    cart_keyboard,
    pickup_time_keyboard,
    confirm_keyboard,
)


router = Router(name="client")


# ===== START =====

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(OrderState.browsing_menu)
    await state.update_data(cart=[])

    menu = await db.get_menu()
    await message.answer(
        "Привет! Это Etlon Coffee\n\n"
        "Выбери напитки из меню:",
        reply_markup=menu_keyboard(menu, [])
    )


# ===== MENU =====

@router.callback_query(F.data.startswith("menu:"), OrderState.browsing_menu)
async def add_to_cart(callback: CallbackQuery, state: FSMContext) -> None:
    item_id = int(callback.data.split(":")[1])
    item = await db.get_menu_item(item_id)

    if not item:
        await callback.answer("Позиция недоступна")
        return

    data = await state.get_data()
    cart: list[dict] = data.get("cart", [])

    # ищем в корзине
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

    cart_items = [CartItem(**c) for c in cart]
    menu = await db.get_menu()

    await callback.message.edit_reply_markup(
        reply_markup=menu_keyboard(menu, cart_items)
    )
    await callback.answer(f"{item.name} добавлен")


# ===== CART =====

@router.callback_query(F.data == "cart:show", OrderState.browsing_menu)
async def show_cart(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    cart = [CartItem(**c) for c in data.get("cart", [])]

    if not cart:
        await callback.answer("Корзина пуста")
        return

    text = "Корзина:\n\n"
    total = 0
    for item in cart:
        line_total = item.price * item.quantity
        total += line_total
        text += f"• {item.name} x{item.quantity} = {line_total}р\n"
    text += f"\nИтого: {total}р"

    await callback.message.edit_text(text, reply_markup=cart_keyboard(cart))


@router.callback_query(F.data == "cart:back", OrderState.browsing_menu)
async def cart_back_to_menu(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    cart = [CartItem(**c) for c in data.get("cart", [])]
    menu = await db.get_menu()

    await callback.message.edit_text(
        "Выбери напитки из меню:",
        reply_markup=menu_keyboard(menu, cart)
    )


@router.callback_query(F.data.startswith("cart:inc:"), OrderState.browsing_menu)
async def cart_increase(callback: CallbackQuery, state: FSMContext) -> None:
    item_id = int(callback.data.split(":")[2])
    data = await state.get_data()
    cart = data.get("cart", [])

    for c in cart:
        if c["menu_item_id"] == item_id:
            c["quantity"] += 1
            break

    await state.update_data(cart=cart)
    await _update_cart_view(callback, cart)


@router.callback_query(F.data.startswith("cart:dec:"), OrderState.browsing_menu)
async def cart_decrease(callback: CallbackQuery, state: FSMContext) -> None:
    item_id = int(callback.data.split(":")[2])
    data = await state.get_data()
    cart = data.get("cart", [])

    # уменьшаем или удаляем
    new_cart = []
    for c in cart:
        if c["menu_item_id"] == item_id:
            if c["quantity"] > 1:
                c["quantity"] -= 1
                new_cart.append(c)
            # иначе не добавляем — удаляем
        else:
            new_cart.append(c)

    await state.update_data(cart=new_cart)

    if new_cart:
        await _update_cart_view(callback, new_cart)
    else:
        # корзина опустела — возврат в меню
        menu = await db.get_menu()
        await callback.message.edit_text(
            "Выбери напитки из меню:",
            reply_markup=menu_keyboard(menu, [])
        )


async def _update_cart_view(callback: CallbackQuery, cart_data: list[dict]) -> None:
    cart = [CartItem(**c) for c in cart_data]
    text = "Корзина:\n\n"
    total = 0
    for item in cart:
        line_total = item.price * item.quantity
        total += line_total
        text += f"• {item.name} x{item.quantity} = {line_total}р\n"
    text += f"\nИтого: {total}р"
    await callback.message.edit_text(text, reply_markup=cart_keyboard(cart))


# ===== CHECKOUT =====

@router.callback_query(F.data == "cart:checkout", OrderState.browsing_menu)
async def checkout(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    cart = data.get("cart", [])

    if not cart:
        await callback.answer("Корзина пуста")
        return

    await state.set_state(OrderState.selecting_time)
    await callback.message.edit_text(
        "Когда заберёшь заказ?",
        reply_markup=pickup_time_keyboard()
    )


# ===== TIME SELECTION =====

@router.callback_query(F.data == "time:back", OrderState.selecting_time)
async def time_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(OrderState.browsing_menu)
    data = await state.get_data()
    cart = [CartItem(**c) for c in data.get("cart", [])]
    await callback.message.edit_text("Корзина:", reply_markup=cart_keyboard(cart))


@router.callback_query(F.data.startswith("time:"), OrderState.selecting_time)
async def select_time(callback: CallbackQuery, state: FSMContext) -> None:
    minutes = callback.data.split(":")[1]
    if minutes == "back":
        return  # обработано выше

    pickup_time = f"через {minutes} мин"
    await state.update_data(pickup_time=pickup_time)
    await state.set_state(OrderState.confirming)

    data = await state.get_data()
    cart = [CartItem(**c) for c in data.get("cart", [])]

    text = "Проверь заказ:\n\n"
    total = 0
    for item in cart:
        line_total = item.price * item.quantity
        total += line_total
        text += f"• {item.name} x{item.quantity} = {line_total}р\n"
    text += f"\nИтого: {total}р"
    text += f"\nЗабор: {pickup_time}"

    await callback.message.edit_text(text, reply_markup=confirm_keyboard())


# ===== CONFIRM =====

@router.callback_query(F.data == "confirm:edit", OrderState.confirming)
async def confirm_edit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(OrderState.browsing_menu)
    data = await state.get_data()
    cart = [CartItem(**c) for c in data.get("cart", [])]
    await callback.message.edit_text("Корзина:", reply_markup=cart_keyboard(cart))


@router.callback_query(F.data == "confirm:yes", OrderState.confirming)
async def confirm_order(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    cart_data = data.get("cart", [])
    pickup_time = data.get("pickup_time", "через 15 мин")

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
            quantity=c["quantity"]
        )
        for c in cart_data
    ]

    order = await db.create_order(
        user_id=user.id,
        user_name=user_name,
        items=items,
        pickup_time=pickup_time
    )

    await state.clear()

    await callback.message.edit_text(
        f"Заказ #{order.id} оформлен!\n\n"
        f"Сумма: {order.total}р\n"
        f"Забор: {pickup_time}\n\n"
        "Мы напишем, когда будет готово.\n"
        "Для нового заказа: /start"
    )
