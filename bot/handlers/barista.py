from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from bot import database as db
from bot.config import settings
from bot.models import OrderStatus
from bot.keyboards import barista_orders_keyboard, barista_order_detail_keyboard


router = Router(name="barista")


def _is_barista(user_id: int) -> bool:
    return settings.is_barista(user_id)


# ===== BARISTA PANEL =====

@router.message(Command("barista"))
async def cmd_barista(message: Message) -> None:
    if not _is_barista(message.from_user.id):
        await message.answer("Доступ только для баристы")
        return

    orders = await db.get_active_orders()
    await message.answer(
        "Панель баристы\n\nАктивные заказы:",
        reply_markup=barista_orders_keyboard(orders)
    )


@router.callback_query(F.data == "barista:refresh")
async def refresh_orders(callback: CallbackQuery) -> None:
    if not _is_barista(callback.from_user.id):
        await callback.answer("Нет доступа")
        return

    orders = await db.get_active_orders()
    await callback.message.edit_text(
        "Панель баристы\n\nАктивные заказы:",
        reply_markup=barista_orders_keyboard(orders)
    )
    await callback.answer("Обновлено")


@router.callback_query(F.data == "barista:list")
async def back_to_list(callback: CallbackQuery) -> None:
    if not _is_barista(callback.from_user.id):
        await callback.answer("Нет доступа")
        return

    orders = await db.get_active_orders()
    await callback.message.edit_text(
        "Панель баристы\n\nАктивные заказы:",
        reply_markup=barista_orders_keyboard(orders)
    )


@router.callback_query(F.data.startswith("barista:order:"))
async def show_order_detail(callback: CallbackQuery) -> None:
    if not _is_barista(callback.from_user.id):
        await callback.answer("Нет доступа")
        return

    order_id = int(callback.data.split(":")[2])
    order = await db.get_order(order_id)

    if not order:
        await callback.answer("Заказ не найден")
        return

    text = f"Заказ #{order.id}\n"
    text += f"Статус: {order.status.display_name}\n"
    text += f"Клиент: {order.user_name}\n"
    text += f"Забор: {order.pickup_time}\n\n"

    for item in order.items:
        text += f"• {item.name} x{item.quantity}\n"

    text += f"\nИтого: {order.total}р"

    await callback.message.edit_text(
        text,
        reply_markup=barista_order_detail_keyboard(order)
    )


@router.callback_query(F.data.startswith("barista:status:"))
async def change_status(callback: CallbackQuery, bot: Bot) -> None:
    if not _is_barista(callback.from_user.id):
        await callback.answer("Нет доступа")
        return

    parts = callback.data.split(":")
    order_id = int(parts[2])
    new_status = OrderStatus(parts[3])

    order = await db.update_order_status(order_id, new_status)

    if not order:
        await callback.answer("Заказ не найден")
        return

    # уведомление клиенту при статусе READY
    if new_status == OrderStatus.READY:
        try:
            await bot.send_message(
                order.user_id,
                f"Заказ #{order.id} готов!\n\n"
                "Можно забирать"
            )
        except Exception:
            pass  # клиент мог заблокировать бота

    await callback.answer(f"Статус: {new_status.display_name}")

    # обновляем детали заказа
    text = f"Заказ #{order.id}\n"
    text += f"Статус: {order.status.display_name}\n"
    text += f"Клиент: {order.user_name}\n"
    text += f"Забор: {order.pickup_time}\n\n"

    for item in order.items:
        text += f"• {item.name} x{item.quantity}\n"

    text += f"\nИтого: {order.total}р"

    await callback.message.edit_text(
        text,
        reply_markup=barista_order_detail_keyboard(order)
    )
