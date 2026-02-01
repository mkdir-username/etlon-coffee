"""Утилиты для обработчиков бота."""
from typing import Any

from aiogram.types import CallbackQuery, Message, InaccessibleMessage, InlineKeyboardMarkup


async def safe_edit_text(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = None,
) -> bool:
    """
    Безопасное редактирование сообщения в callback.
    Возвращает True если успешно, False если сообщение недоступно.
    """
    if not callback.message:
        await callback.answer(text[:200])
        return False
    if isinstance(callback.message, InaccessibleMessage):
        await callback.answer(text[:200])
        return False
    await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    return True


async def safe_edit_reply_markup(
    callback: CallbackQuery,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> bool:
    """
    Безопасное редактирование reply_markup в callback.
    Возвращает True если успешно, False если сообщение недоступно.
    """
    if not callback.message:
        await callback.answer()
        return False
    if isinstance(callback.message, InaccessibleMessage):
        await callback.answer()
        return False
    await callback.message.edit_reply_markup(reply_markup=reply_markup)
    return True


def get_callback_data(callback: CallbackQuery) -> str | None:
    """Безопасное получение callback.data."""
    return callback.data


def get_user_id(callback: CallbackQuery) -> int | None:
    """Безопасное получение user_id из callback."""
    return callback.from_user.id if callback.from_user else None


def get_message_user_id(message: Message) -> int | None:
    """Безопасное получение user_id из message."""
    return message.from_user.id if message.from_user else None
