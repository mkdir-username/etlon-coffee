"""Pytest фикстуры для тестов Etlon Coffee Bot."""
import asyncio
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest
import pytest_asyncio
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey

from bot.models import (
    CartItem,
    MenuItem,
    Modifier,
    Order,
    OrderItem,
    OrderStatus,
)


# Event loop для async тестов
@pytest.fixture(scope="session")
def event_loop():
    """Создаёт event loop для сессии тестов."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Путь к временной БД."""
    return tmp_path / "test_etlon.db"


@pytest_asyncio.fixture
async def test_db(temp_db_path: Path, monkeypatch):
    """
    Создаёт временную тестовую БД со всеми таблицами.
    Патчит DB_PATH в модулях database и loyalty.
    """
    # Патчим DB_PATH до импорта
    monkeypatch.setattr("bot.database.DB_PATH", temp_db_path)
    monkeypatch.setattr("bot.loyalty.DB_PATH", temp_db_path)
    monkeypatch.setattr("bot.stats.DB_PATH", temp_db_path)

    from bot import database as db

    # Создаём таблицы
    async with aiosqlite.connect(temp_db_path) as conn:
        await conn.executescript(db.SCHEMA)
        await conn.executescript(db.LOYALTY_SCHEMA)
        await conn.executescript(db.MODIFIERS_SCHEMA)
        await conn.commit()

    yield temp_db_path

    # Cleanup
    if temp_db_path.exists():
        temp_db_path.unlink()


@pytest_asyncio.fixture
async def populated_db(test_db: Path, sample_menu_items: list[dict]):
    """
    Тестовая БД с предзаполненным меню.
    """
    async with aiosqlite.connect(test_db) as conn:
        for item in sample_menu_items:
            await conn.execute(
                "INSERT INTO menu_items (id, name, price, available) VALUES (?, ?, ?, ?)",
                (item["id"], item["name"], item["price"], item.get("available", 1))
            )
        await conn.commit()

    yield test_db


@pytest.fixture
def sample_menu_items() -> list[dict]:
    """Примеры позиций меню для тестов."""
    return [
        {"id": 1, "name": "Эспрессо", "price": 120, "available": 1},
        {"id": 2, "name": "Американо", "price": 150, "available": 1},
        {"id": 3, "name": "Латте", "price": 220, "available": 1},
        {"id": 4, "name": "Капучино", "price": 200, "available": 1},
        {"id": 5, "name": "Раф", "price": 280, "available": 0},  # недоступен
    ]


@pytest.fixture
def sample_modifiers() -> list[dict]:
    """Примеры модификаторов для тестов."""
    return [
        {"id": 1, "name": "Ванильный сироп", "category": "syrup", "price": 50},
        {"id": 2, "name": "Карамельный сироп", "category": "syrup", "price": 50},
        {"id": 3, "name": "Овсяное молоко", "category": "milk", "price": 60},
        {"id": 4, "name": "Кокосовое молоко", "category": "milk", "price": 70},
        {"id": 5, "name": "Двойной шот", "category": "extra", "price": 80},
    ]


@pytest.fixture
def sample_sizes() -> list[dict]:
    """Примеры размеров для тестов."""
    return [
        {"size": "S", "size_name": "Маленький 250мл", "price_diff": 0},
        {"size": "M", "size_name": "Средний 350мл", "price_diff": 40},
        {"size": "L", "size_name": "Большой 450мл", "price_diff": 80},
    ]


@pytest.fixture
def sample_cart() -> list[CartItem]:
    """Примеры позиций корзины для тестов."""
    return [
        CartItem(
            menu_item_id=1,
            name="Эспрессо",
            price=120,
            quantity=2,
        ),
        CartItem(
            menu_item_id=3,
            name="Латте",
            price=260,  # 220 + 40 за размер M
            quantity=1,
            size="M",
            size_name="Средний 350мл",
            modifier_ids=[1],
            modifier_names=["Ванильный сироп"],
            modifiers_price=50,
        ),
    ]


@pytest.fixture
def sample_cart_dicts() -> list[dict]:
    """Примеры позиций корзины в формате dict (как в FSM state)."""
    return [
        {
            "menu_item_id": 1,
            "name": "Эспрессо",
            "price": 120,
            "quantity": 2,
        },
        {
            "menu_item_id": 3,
            "name": "Латте",
            "price": 260,
            "quantity": 1,
            "size": "M",
            "size_name": "Средний 350мл",
            "modifier_ids": [1],
            "modifier_names": ["Ванильный сироп"],
            "modifiers_price": 50,
        },
    ]


@pytest.fixture
def sample_order_items() -> list[OrderItem]:
    """Примеры позиций заказа."""
    return [
        OrderItem(
            menu_item_id=1,
            name="Эспрессо",
            price=120,
            quantity=2,
        ),
        OrderItem(
            menu_item_id=3,
            name="Латте",
            price=260,
            quantity=1,
            size="M",
            size_name="Средний 350мл",
            modifier_ids=[1],
            modifier_names=["Ванильный сироп"],
            modifiers_price=50,
        ),
    ]


@pytest.fixture
def sample_order(sample_order_items: list[OrderItem]) -> Order:
    """Пример заказа для тестов."""
    return Order(
        id=1,
        user_id=123456,
        user_name="Test User",
        items=sample_order_items,
        total=500,
        pickup_time="через 15 мин",
        status=OrderStatus.CONFIRMED,
        created_at=datetime(2026, 2, 1, 12, 0, 0),
    )


@pytest.fixture
def mock_bot() -> MagicMock:
    """Мок aiogram Bot для тестов."""
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock())
    return bot


@pytest.fixture
def mock_callback() -> MagicMock:
    """Мок CallbackQuery для тестов handlers."""
    callback = MagicMock()
    callback.from_user = MagicMock()
    callback.from_user.id = 123456
    callback.from_user.full_name = "Test User"
    callback.from_user.username = "testuser"
    callback.data = ""
    callback.message = MagicMock()
    callback.message.edit_text = AsyncMock()
    callback.message.edit_reply_markup = AsyncMock()
    callback.answer = AsyncMock()
    return callback


@pytest.fixture
def mock_message() -> MagicMock:
    """Мок Message для тестов handlers."""
    message = MagicMock()
    message.from_user = MagicMock()
    message.from_user.id = 123456
    message.from_user.full_name = "Test User"
    message.from_user.username = "testuser"
    message.text = ""
    message.answer = AsyncMock()
    return message


@pytest.fixture
def mock_state() -> MagicMock:
    """Мок FSMContext для тестов handlers."""
    state = MagicMock()
    state.get_state = AsyncMock(return_value=None)
    state.set_state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.update_data = AsyncMock()
    state.clear = AsyncMock()
    return state


# ===== E2E фикстуры =====


@pytest.fixture
def memory_storage() -> MemoryStorage:
    """In-memory storage для FSM в E2E тестах."""
    return MemoryStorage()


@pytest_asyncio.fixture
async def fsm_context_factory(memory_storage: MemoryStorage):
    """
    Фабрика FSMContext с персистентным state между вызовами.
    
    Использование:
        state = await fsm_context_factory(user_id=123)
        await state.set_state(OrderState.browsing_menu)
    """
    async def _get_context(user_id: int, chat_id: int | None = None) -> FSMContext:
        if chat_id is None:
            chat_id = user_id
        key = StorageKey(bot_id=1, chat_id=chat_id, user_id=user_id)
        return FSMContext(storage=memory_storage, key=key)
    return _get_context


@pytest.fixture
def make_callback(mock_bot: MagicMock):
    """
    Фабрика для создания CallbackQuery с разными data.
    
    Использование:
        cb = make_callback(user_id=123, data="menu:1")
    """
    def _make(user_id: int, data: str, full_name: str = "Test User") -> MagicMock:
        cb = MagicMock()
        cb.from_user = MagicMock()
        cb.from_user.id = user_id
        cb.from_user.full_name = full_name
        cb.from_user.username = f"user_{user_id}"
        cb.data = data
        cb.message = MagicMock()
        cb.message.edit_text = AsyncMock()
        cb.message.edit_reply_markup = AsyncMock()
        cb.message.delete = AsyncMock()
        cb.message.chat = MagicMock()
        cb.message.chat.id = user_id
        cb.answer = AsyncMock()
        cb.bot = mock_bot
        return cb
    return _make


@pytest.fixture
def make_message(mock_bot: MagicMock):
    """
    Фабрика для создания Message с разными параметрами.
    
    Использование:
        msg = make_message(user_id=123, text="/start")
    """
    def _make(user_id: int, text: str, full_name: str = "Test User") -> MagicMock:
        msg = MagicMock()
        msg.from_user = MagicMock()
        msg.from_user.id = user_id
        msg.from_user.full_name = full_name
        msg.from_user.username = f"user_{user_id}"
        msg.text = text
        msg.chat = MagicMock()
        msg.chat.id = user_id
        msg.answer = AsyncMock()
        msg.reply = AsyncMock()
        msg.bot = mock_bot
        return msg
    return _make


@pytest_asyncio.fixture
async def e2e_context(populated_db: Path, mock_bot: MagicMock, memory_storage: MemoryStorage):
    """
    Полный контекст для E2E тестов: БД с меню + бот + storage.
    
    Использование:
        async with e2e_context as ctx:
            state = await ctx["get_state"](user_id)
    """
    async def _get_state(user_id: int) -> FSMContext:
        key = StorageKey(bot_id=1, chat_id=user_id, user_id=user_id)
        return FSMContext(storage=memory_storage, key=key)
    
    yield {
        "db": populated_db,
        "bot": mock_bot,
        "storage": memory_storage,
        "get_state": _get_state,
    }


@pytest_asyncio.fixture
async def populated_db_with_modifiers(
    populated_db: Path,
    sample_modifiers: list[dict],
    sample_sizes: list[dict],
):
    """
    Тестовая БД с меню, модификаторами и размерами.
    """
    async with aiosqlite.connect(populated_db) as conn:
        # Добавляем модификаторы
        for mod in sample_modifiers:
            await conn.execute(
                "INSERT INTO modifiers (id, name, category, price, is_available) VALUES (?, ?, ?, ?, 1)",
                (mod["id"], mod["name"], mod["category"], mod["price"])
            )
        
        # Связываем модификаторы с позициями меню (все позиции поддерживают все модификаторы)
        for item_id in [1, 2, 3, 4, 5]:
            for mod in sample_modifiers:
                await conn.execute(
                    "INSERT INTO menu_item_modifiers (menu_item_id, modifier_id) VALUES (?, ?)",
                    (item_id, mod["id"])
                )
        
        # Добавляем размеры для всех позиций
        for item_id in [1, 2, 3, 4, 5]:
            for size in sample_sizes:
                await conn.execute(
                    "INSERT INTO menu_item_sizes (menu_item_id, size, size_name, price_diff) VALUES (?, ?, ?, ?)",
                    (item_id, size["size"], size["size_name"], size["price_diff"])
                )
        
        await conn.commit()
    
    yield populated_db


# Вспомогательные функции для тестов

async def insert_order(
    db_path: Path,
    user_id: int,
    user_name: str,
    items: list[dict],
    total: int,
    pickup_time: str = "через 15 мин",
    status: str = "confirmed",
    created_at: datetime | None = None,
) -> int:
    """Вставляет заказ в БД и возвращает его ID."""
    if created_at is None:
        created_at = datetime.now()

    items_json = json.dumps(items, ensure_ascii=False)

    async with aiosqlite.connect(db_path) as conn:
        cursor = await conn.execute(
            """INSERT INTO orders (user_id, user_name, items, total, pickup_time, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, user_name, items_json, total, pickup_time, status, created_at)
        )
        await conn.commit()
        return cursor.lastrowid


async def insert_loyalty(
    db_path: Path,
    user_id: int,
    points: int = 0,
    stamps: int = 0,
    total_orders: int = 0,
    total_spent: int = 0,
) -> None:
    """Вставляет запись лояльности в БД."""
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            """INSERT INTO loyalty (user_id, points, stamps, total_orders, total_spent)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, points, stamps, total_orders, total_spent)
        )
        await conn.commit()


async def insert_points_history(
    db_path: Path,
    user_id: int,
    amount: int,
    operation: str,
    order_id: int | None = None,
    description: str | None = None,
) -> None:
    """Вставляет запись в историю баллов."""
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            """INSERT INTO points_history (user_id, amount, operation, order_id, description)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, amount, operation, order_id, description)
        )
        await conn.commit()


async def get_loyalty(db_path: Path, user_id: int) -> dict | None:
    """Получает данные лояльности из БД."""
    async with aiosqlite.connect(db_path) as conn:
        cursor = await conn.execute(
            "SELECT points, stamps, total_orders, total_spent FROM loyalty WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        if row:
            return {
                "points": row[0],
                "stamps": row[1],
                "total_orders": row[2],
                "total_spent": row[3],
            }
        return None


async def get_user_orders(db_path: Path, user_id: int, limit: int = 10) -> list[dict]:
    """Получает заказы пользователя из БД."""
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT id, user_id, user_name, items, total, pickup_time, status, created_at
               FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT ?""",
            (user_id, limit)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_order_by_id(db_path: Path, order_id: int) -> dict | None:
    """Получает заказ по ID."""
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT id, user_id, user_name, items, total, pickup_time, status, created_at
               FROM orders WHERE id = ?""",
            (order_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def add_favorite(db_path: Path, user_id: int, menu_item_id: int) -> None:
    """Добавляет позицию в избранное."""
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO favorites (user_id, menu_item_id) VALUES (?, ?)",
            (user_id, menu_item_id)
        )
        await conn.commit()


async def get_favorites(db_path: Path, user_id: int) -> list[int]:
    """Получает список ID избранных позиций."""
    async with aiosqlite.connect(db_path) as conn:
        cursor = await conn.execute(
            "SELECT menu_item_id FROM favorites WHERE user_id = ?",
            (user_id,)
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]
