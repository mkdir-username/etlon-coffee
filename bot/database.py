import json
import aiosqlite
from datetime import datetime
from pathlib import Path
from bot.models import MenuItem, Order, OrderItem, OrderStatus


DB_PATH = Path(__file__).parent.parent / "etlon.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS menu_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    price INTEGER NOT NULL,
    available INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    user_name TEXT NOT NULL,
    items TEXT NOT NULL,
    total INTEGER NOT NULL,
    pickup_time TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


async def get_db() -> aiosqlite.Connection:
    return await aiosqlite.connect(DB_PATH)


async def ensure_tables() -> None:
    """Создает таблицы, если не существуют (idempotent)"""
    async with await get_db() as db:
        await db.executescript(SCHEMA)
        await db.commit()


# ===== MENU =====

async def get_menu() -> list[MenuItem]:
    async with await get_db() as db:
        cursor = await db.execute(
            "SELECT id, name, price, available FROM menu_items WHERE available = 1"
        )
        rows = await cursor.fetchall()
        return [MenuItem(id=r[0], name=r[1], price=r[2], available=r[3]) for r in rows]


async def get_menu_item(item_id: int) -> MenuItem | None:
    async with await get_db() as db:
        cursor = await db.execute(
            "SELECT id, name, price, available FROM menu_items WHERE id = ?",
            (item_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return MenuItem(id=row[0], name=row[1], price=row[2], available=row[3])


# ===== ORDERS =====

async def create_order(
    user_id: int,
    user_name: str,
    items: list[OrderItem],
    pickup_time: str
) -> Order:
    total = sum(item.price * item.quantity for item in items)
    items_json = json.dumps([i.model_dump() for i in items], ensure_ascii=False)
    created_at = datetime.now()

    async with await get_db() as db:
        cursor = await db.execute(
            """INSERT INTO orders (user_id, user_name, items, total, pickup_time, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, user_name, items_json, total, pickup_time, OrderStatus.CONFIRMED.value, created_at)
        )
        await db.commit()
        order_id = cursor.lastrowid

    return Order(
        id=order_id,
        user_id=user_id,
        user_name=user_name,
        items=items,
        total=total,
        pickup_time=pickup_time,
        status=OrderStatus.CONFIRMED,
        created_at=created_at
    )


async def get_order(order_id: int) -> Order | None:
    async with await get_db() as db:
        cursor = await db.execute(
            "SELECT id, user_id, user_name, items, total, pickup_time, status, created_at FROM orders WHERE id = ?",
            (order_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return _row_to_order(row)


async def get_active_orders() -> list[Order]:
    """Активные заказы для бариста (не COMPLETED, не CANCELLED)"""
    async with await get_db() as db:
        cursor = await db.execute(
            """SELECT id, user_id, user_name, items, total, pickup_time, status, created_at
               FROM orders
               WHERE status NOT IN (?, ?)
               ORDER BY created_at ASC""",
            (OrderStatus.COMPLETED.value, OrderStatus.CANCELLED.value)
        )
        rows = await cursor.fetchall()
        return [_row_to_order(r) for r in rows]


async def update_order_status(order_id: int, status: OrderStatus) -> Order | None:
    async with await get_db() as db:
        await db.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            (status.value, order_id)
        )
        await db.commit()
    return await get_order(order_id)


def _row_to_order(row: tuple) -> Order:
    items_data = json.loads(row[3])
    items = [OrderItem(**i) for i in items_data]
    return Order(
        id=row[0],
        user_id=row[1],
        user_name=row[2],
        items=items,
        total=row[4],
        pickup_time=row[5],
        status=OrderStatus(row[6]),
        created_at=datetime.fromisoformat(row[7]) if isinstance(row[7], str) else row[7]
    )
