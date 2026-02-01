import logging
from datetime import date, timedelta

from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery

from bot import database as db
from bot.config import settings
from bot.models import OrderStatus
from bot.keyboards import (
    barista_orders_keyboard,
    barista_order_detail_keyboard,
    menu_manage_keyboard,
)
from bot.stats import get_daily_stats, get_weekly_stats, format_stats, format_weekly_stats

logger = logging.getLogger(__name__)


router = Router(name="barista")


def _is_barista(user_id: int) -> bool:
    return settings.is_barista(user_id)


# ===== BARISTA PANEL =====

@router.message(Command("barista"))
async def cmd_barista(message: Message) -> None:
    if not _is_barista(message.from_user.id):
        logger.warning(
            "unauthorized_access",
            extra={
                "user_id": message.from_user.id,
                "username": message.from_user.username,
                "command": "barista"
            }
        )
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

    text = _format_barista_order_detail(order)

    await callback.message.edit_text(
        text,
        reply_markup=barista_order_detail_keyboard(order)
    )


def _format_barista_order_detail(order) -> str:
    """Форматирует детали заказа для баристы с модификаторами"""
    text = f"Заказ #{order.id}\n"
    text += f"Статус: {order.status.display_name}\n"
    text += f"Клиент: {order.user_name}\n"
    text += f"Забор: {order.pickup_time}\n\n"

    for item in order.items:
        size_suffix = f" ({item.size})" if item.size else ""
        text += f"* {item.name}{size_suffix} x{item.quantity}\n"
        if item.modifier_names:
            mods_str = ", ".join(item.modifier_names)
            text += f"  + {mods_str}\n"
        if item.comment:
            text += f"  {item.comment}\n"

    text += f"\nИтого: {order.total}\u20bd"
    return text


@router.callback_query(F.data.startswith("barista:status:"))
async def change_status(callback: CallbackQuery, bot: Bot) -> None:
    if not _is_barista(callback.from_user.id):
        await callback.answer("Нет доступа")
        return

    parts = callback.data.split(":")
    order_id = int(parts[2])
    new_status = OrderStatus(parts[3])

    old_order = await db.get_order(order_id)
    order = await db.update_order_status(order_id, new_status)

    if not order:
        await callback.answer("Заказ не найден")
        return

    old_status = old_order.status.value if old_order else "unknown"
    logger.info(
        "status_changed",
        extra={
            "barista_id": callback.from_user.id,
            "order_id": order_id,
            "old_status": old_status,
            "new_status": new_status.value
        }
    )

    # уведомление клиенту при статусе READY
    if new_status == OrderStatus.READY:
        try:
            await bot.send_message(
                order.user_id,
                f"Заказ #{order.id} готов!\n\n"
                "Можно забирать"
            )
            logger.info(
                "notification_sent",
                extra={"order_id": order.id, "user_id": order.user_id}
            )
        except Exception as e:
            logger.error(
                "notification_failed",
                extra={
                    "order_id": order.id,
                    "user_id": order.user_id,
                    "error": str(e)
                },
                exc_info=True
            )

    await callback.answer(f"Статус: {new_status.display_name}")

    # обновляем детали заказа
    text = _format_barista_order_detail(order)

    await callback.message.edit_text(
        text,
        reply_markup=barista_order_detail_keyboard(order)
    )


# ===== STATISTICS =====

@router.message(Command("stats"))
async def cmd_stats(message: Message, command: CommandObject) -> None:
    if not _is_barista(message.from_user.id):
        logger.warning(
            "unauthorized_access",
            extra={
                "user_id": message.from_user.id,
                "username": message.from_user.username,
                "command": "stats"
            }
        )
        await message.answer("Доступ только для баристы")
        return

    arg = command.args.strip().lower() if command.args else ""

    if arg == "week":
        logger.info(
            "stats_requested",
            extra={
                "barista_id": message.from_user.id,
                "period": "week"
            }
        )
        stats = await get_weekly_stats(days=7)
        await message.answer(format_weekly_stats(stats))
        return

    target_date = date.today()
    if arg == "yesterday":
        target_date = date.today() - timedelta(days=1)

    logger.info(
        "stats_requested",
        extra={
            "barista_id": message.from_user.id,
            "date": target_date.isoformat()
        }
    )

    stats = await get_daily_stats(target_date)
    await message.answer(format_stats(stats))


# ===== MENU MANAGEMENT =====

def _menu_manage_text() -> str:
    return (
        "⚙️ Управление меню\n\n"
        "Нажмите на позицию, чтобы скрыть/показать:\n\n"
        "💡 Скрытые позиции не видны клиентам"
    )


@router.message(Command("menu_manage"))
async def cmd_menu_manage(message: Message) -> None:
    if not _is_barista(message.from_user.id):
        logger.warning(
            "unauthorized_access",
            extra={
                "user_id": message.from_user.id,
                "username": message.from_user.username,
                "command": "menu_manage"
            }
        )
        await message.answer("Доступ только для баристы")
        return

    items = await db.get_all_menu_items()
    await message.answer(
        _menu_manage_text(),
        reply_markup=menu_manage_keyboard(items)
    )


@router.callback_query(F.data == "menu_manage:refresh")
async def refresh_menu_manage(callback: CallbackQuery) -> None:
    if not _is_barista(callback.from_user.id):
        await callback.answer("Нет доступа")
        return

    items = await db.get_all_menu_items()
    await callback.message.edit_text(
        _menu_manage_text(),
        reply_markup=menu_manage_keyboard(items)
    )
    await callback.answer("Обновлено")


@router.callback_query(F.data.startswith("menu_toggle:"))
async def toggle_menu_item(callback: CallbackQuery) -> None:
    if not _is_barista(callback.from_user.id):
        await callback.answer("Нет доступа")
        return

    item_id = int(callback.data.split(":")[1])
    item = await db.toggle_menu_item_availability(item_id)

    if not item:
        await callback.answer("Позиция не найдена")
        return

    new_status = "доступна" if item.available else "скрыта"
    logger.info(
        "menu_item_toggled",
        extra={
            "barista_id": callback.from_user.id,
            "item_id": item_id,
            "item_name": item.name,
            "available": item.available
        }
    )

    items = await db.get_all_menu_items()
    await callback.message.edit_reply_markup(
        reply_markup=menu_manage_keyboard(items)
    )
    await callback.answer(f"{item.name}: {new_status}")