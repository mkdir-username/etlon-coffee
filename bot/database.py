import json
import logging
from typing import Any

import aiosqlite
from datetime import datetime
from pathlib import Path
from bot.models import MenuItem, Order, OrderItem, OrderStatus

logger = logging.getLogger(__name__)


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

CREATE TABLE IF NOT EXISTS favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    menu_item_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, menu_item_id)
);

CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id);
"""

LOYALTY_SCHEMA = """
CREATE TABLE IF NOT EXISTS loyalty (
    user_id INTEGER PRIMARY KEY,
    points INTEGER DEFAULT 0,
    stamps INTEGER DEFAULT 0,
    total_orders INTEGER DEFAULT 0,
    total_spent INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS points_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    operation TEXT NOT NULL,
    order_id INTEGER,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES loyalty(user_id)
);

CREATE INDEX IF NOT EXISTS idx_points_history_user ON points_history(user_id);
"""

MODIFIERS_SCHEMA = """
-- Размеры для позиций меню
CREATE TABLE IF NOT EXISTS menu_item_sizes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    menu_item_id INTEGER NOT NULL,
    size TEXT NOT NULL,
    size_name TEXT NOT NULL,
    price_diff INTEGER DEFAULT 0,
    available INTEGER DEFAULT 1,
    FOREIGN KEY (menu_item_id) REFERENCES menu_items(id)
);

-- Модификаторы (сиропы, молоко и т.д.)
CREATE TABLE IF NOT EXISTS modifiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price INTEGER NOT NULL DEFAULT 0,
    is_available BOOLEAN DEFAULT 1,
    sort_order INTEGER DEFAULT 0
);

-- Связь модификаторов с позициями меню
CREATE TABLE IF NOT EXISTS menu_item_modifiers (
    menu_item_id INTEGER NOT NULL,
    modifier_id INTEGER NOT NULL,
    PRIMARY KEY (menu_item_id, modifier_id),
    FOREIGN KEY (menu_item_id) REFERENCES menu_items(id),
    FOREIGN KEY (modifier_id) REFERENCES modifiers(id)
);

-- Модификаторы в заказе
CREATE TABLE IF NOT EXISTS order_item_modifiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    item_index INTEGER NOT NULL,
    modifier_id INTEGER NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(id),
    FOREIGN KEY (modifier_id) REFERENCES modifiers(id)
);

CREATE INDEX IF NOT EXISTS idx_sizes_menu ON menu_item_sizes(menu_item_id);
CREATE INDEX IF NOT EXISTS idx_order_mods ON order_item_modifiers(order_id);
CREATE INDEX IF NOT EXISTS idx_modifiers_category ON modifiers(category);
"""


async def ensure_tables() -> None:
    """Создает таблицы, если не существуют (idempotent)"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.executescript(LOYALTY_SCHEMA)
        await db.executescript(MODIFIERS_SCHEMA)
        await db.commit()


# ===== MENU =====

async def get_menu() -> list[MenuItem]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, name, price, available FROM menu_items WHERE available = 1"
        )
        rows = await cursor.fetchall()
        return [MenuItem(id=r[0], name=r[1], price=r[2], available=r[3]) for r in rows]


async def get_menu_item(item_id: int) -> MenuItem | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, name, price, available FROM menu_items WHERE id = ?",
            (item_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return MenuItem(id=row[0], name=row[1], price=row[2], available=bool(row[3]))


async def get_menu_item_sizes(menu_item_id: int) -> list[dict]:
    """
    Возвращает размеры для позиции меню.
    Returns: [{"size": "S", "size_name": "Маленький 250мл", "price_diff": 0}, ...]
    Если размеров нет — пустой список.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """SELECT size, size_name, price_diff
               FROM menu_item_sizes
               WHERE menu_item_id = ? AND available = 1
               ORDER BY price_diff ASC""",
            (menu_item_id,)
        )
        rows = await cursor.fetchall()
        return [
            {"size": r[0], "size_name": r[1], "price_diff": r[2]}
            for r in rows
        ]


async def get_all_menu_items() -> list[MenuItem]:
    """Все позиции включая недоступные (available=0)"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, name, price, available FROM menu_items ORDER BY id"
        )
        rows = await cursor.fetchall()
        return [MenuItem(id=r[0], name=r[1], price=r[2], available=bool(r[3])) for r in rows]


async def toggle_menu_item_availability(item_id: int) -> MenuItem | None:
    """Переключает available между 0 и 1, возвращает обновленную позицию"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE menu_items SET available = 1 - available WHERE id = ?",
            (item_id,)
        )
        await db.commit()
    return await get_menu_item(item_id)


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

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            cursor = await db.execute(
                """INSERT INTO orders (user_id, user_name, items, total, pickup_time, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, user_name, items_json, total, pickup_time, OrderStatus.CONFIRMED.value, created_at)
            )
            await db.commit()
            order_id = cursor.lastrowid

            logger.debug(
                "db_insert_order",
                extra={
                    "order_id": order_id,
                    "user_id": user_id,
                    "items_count": len(items)
                }
            )
        except Exception as e:
            logger.error(
                "db_insert_failed",
                extra={"user_id": user_id, "error": str(e)},
                exc_info=True
            )
            raise

    return Order(
        id=order_id or 0,
        user_id=user_id,
        user_name=user_name,
        items=items,
        total=total,
        pickup_time=pickup_time,
        status=OrderStatus.CONFIRMED,
        created_at=created_at
    )


async def get_order(order_id: int) -> Order | None:
    async with aiosqlite.connect(DB_PATH) as db:
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
    async with aiosqlite.connect(DB_PATH) as db:
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
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            (status.value, order_id)
        )
        await db.commit()
    return await get_order(order_id)


async def get_user_orders(user_id: int, limit: int = 5, offset: int = 0) -> tuple[list[Order], int]:
    """Возвращает (orders, total_count) для пагинации"""
    async with aiosqlite.connect(DB_PATH) as db:
        # total count
        cursor = await db.execute(
            "SELECT COUNT(*) FROM orders WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        total_count = row[0] if row else 0

        # orders
        cursor = await db.execute(
            """SELECT id, user_id, user_name, items, total, pickup_time, status, created_at
               FROM orders
               WHERE user_id = ?
               ORDER BY created_at DESC
               LIMIT ? OFFSET ?""",
            (user_id, limit, offset)
        )
        rows = await cursor.fetchall()
        orders = [_row_to_order(r) for r in rows]

        logger.debug(
            "get_user_orders",
            extra={"user_id": user_id, "total": total_count, "returned": len(orders), "offset": offset}
        )

        return orders, total_count


def _row_to_order(row: Any) -> Order:
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


# ===== FAVORITES =====

async def add_favorite(user_id: int, menu_item_id: int) -> bool:
    """Добавляет позицию в избранное. Возвращает True если добавлено, False если уже было."""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO favorites (user_id, menu_item_id) VALUES (?, ?)",
                (user_id, menu_item_id)
            )
            await db.commit()
            logger.debug(
                "favorite_added",
                extra={"user_id": user_id, "menu_item_id": menu_item_id}
            )
            return True
        except aiosqlite.IntegrityError:
            # UNIQUE constraint — уже в избранном
            return False


async def remove_favorite(user_id: int, menu_item_id: int) -> bool:
    """Удаляет позицию из избранного. Возвращает True если удалено."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM favorites WHERE user_id = ? AND menu_item_id = ?",
            (user_id, menu_item_id)
        )
        await db.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.debug(
                "favorite_removed",
                extra={"user_id": user_id, "menu_item_id": menu_item_id}
            )
        return deleted


async def get_favorites(user_id: int) -> list[MenuItem]:
    """Возвращает список избранных позиций меню (только доступные)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """SELECT m.id, m.name, m.price, m.available
               FROM favorites f
               JOIN menu_items m ON f.menu_item_id = m.id
               WHERE f.user_id = ? AND m.available = 1
               ORDER BY f.created_at DESC""",
            (user_id,)
        )
        rows = await cursor.fetchall()
        return [MenuItem(id=r[0], name=r[1], price=r[2], available=bool(r[3])) for r in rows]


async def is_favorite(user_id: int, menu_item_id: int) -> bool:
    """Проверяет, находится ли позиция в избранном."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM favorites WHERE user_id = ? AND menu_item_id = ?",
            (user_id, menu_item_id)
        )
        row = await cursor.fetchone()
        return row is not None


async def get_user_favorite_ids(user_id: int) -> set[int]:
    """Возвращает set ID избранных позиций для быстрой проверки."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT menu_item_id FROM favorites WHERE user_id = ?",
            (user_id,)
        )
        rows = await cursor.fetchall()
        return {r[0] for r in rows}


async def cancel_order_by_client(order_id: int, user_id: int) -> tuple[bool, str]:
    """
    Отменяет заказ клиентом.
    Возвращает (success, message).
    Проверяет: заказ существует, принадлежит user_id, статус CONFIRMED.
    Использует BEGIN IMMEDIATE для атомарности.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # BEGIN IMMEDIATE блокирует БД от других записей
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                "SELECT user_id, status FROM orders WHERE id = ?",
                (order_id,)
            )
            row = await cursor.fetchone()

            if not row:
                await db.rollback()
                logger.warning(
                    "cancel_order_not_found",
                    extra={"order_id": order_id, "user_id": user_id}
                )
                return False, "Заказ не найден."

            owner_id, current_status = row[0], row[1]

            if owner_id != user_id:
                await db.rollback()
                logger.warning(
                    "cancel_order_access_denied",
                    extra={"order_id": order_id, "user_id": user_id, "owner_id": owner_id}
                )
                return False, "Заказ не найден."

            if current_status != OrderStatus.CONFIRMED.value:
                await db.rollback()
                logger.info(
                    "cancel_order_wrong_status",
                    extra={"order_id": order_id, "user_id": user_id, "status": current_status}
                )
                return False, "Заказ уже в работе и не может быть отменён."

            # Отменяем
            await db.execute(
                "UPDATE orders SET status = ? WHERE id = ?",
                (OrderStatus.CANCELLED.value, order_id)
            )
            await db.commit()

            logger.info(
                "order_cancelled_by_client",
                extra={"order_id": order_id, "user_id": user_id, "old_status": current_status}
            )
            return True, f"Заказ #{order_id} отменён."

        except Exception as e:
            await db.rollback()
            logger.error(
                "cancel_order_failed",
                extra={"order_id": order_id, "user_id": user_id, "error": str(e)},
                exc_info=True
            )
            raise


# ===== REPEAT ORDER =====

async def get_order_items_with_availability(order_id: int) -> list[tuple[OrderItem, bool]]:
    """
    Возвращает позиции заказа с флагом доступности.
    Каждый элемент: (OrderItem, available: bool)
    """
    order = await get_order(order_id)
    if not order:
        return []

    result: list[tuple[OrderItem, bool]] = []
    async with aiosqlite.connect(DB_PATH) as db:
        for item in order.items:
            cursor = await db.execute(
                "SELECT available FROM menu_items WHERE id = ?",
                (item.menu_item_id,)
            )
            row = await cursor.fetchone()
            # позиция доступна если существует и available=1
            available = bool(row and row[0])
            result.append((item, available))

    logger.debug(
        "get_order_items_with_availability",
        extra={
            "order_id": order_id,
            "total_items": len(result),
            "available_count": sum(1 for _, avail in result if avail)
        }
    )

    return result


async def get_order_items_for_repeat(order_id: int) -> list[dict]:
    """
    Получить позиции заказа для повтора.
    Проверяет доступность каждой позиции в текущем меню.
    
    Returns:
        [
            {
                'menu_item_id': int,
                'name': str,
                'price': int,
                'quantity': int,
                'is_available': bool,
                'size': str | None,
                'size_name': str | None,
                'modifier_ids': list[int],
                'modifier_names': list[str],
                'modifiers_price': int,
            }
        ]
    """
    order = await get_order(order_id)
    if not order:
        return []
    
    result: list[dict] = []
    async with aiosqlite.connect(DB_PATH) as db:
        for item in order.items:
            cursor = await db.execute(
                "SELECT available FROM menu_items WHERE id = ?",
                (item.menu_item_id,)
            )
            row = await cursor.fetchone()
            is_available = bool(row and row[0])
            
            result.append({
                "menu_item_id": item.menu_item_id,
                "name": item.name,
                "price": item.price,
                "quantity": item.quantity,
                "is_available": is_available,
                "size": item.size,
                "size_name": item.size_name,
                "modifier_ids": item.modifier_ids,
                "modifier_names": item.modifier_names,
                "modifiers_price": item.modifiers_price,
            })
    
    logger.debug(
        "get_order_items_for_repeat",
        extra={
            "order_id": order_id,
            "total_items": len(result),
            "available_count": sum(1 for i in result if i["is_available"])
        }
    )
    
    return result


# ===== SIZES =====

MODIFIERS_JSON = Path(__file__).parent.parent / "data" / "modifiers.json"


async def init_default_sizes() -> None:
    """
    Инициализирует размеры по умолчанию для всех позиций меню.
    Загружает из data/modifiers.json и применяет ко всем menu_items.
    Idempotent: не дублирует существующие записи.
    """
    if not MODIFIERS_JSON.exists():
        logger.warning("modifiers_json_not_found", extra={"path": str(MODIFIERS_JSON)})
        return

    with open(MODIFIERS_JSON, encoding="utf-8") as f:
        data = json.load(f)

    default_sizes = data.get("sizes", {}).get("default", [])
    if not default_sizes:
        logger.info("no_default_sizes_in_json")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        # Получаем все menu_items
        cursor = await db.execute("SELECT id FROM menu_items")
        menu_ids = [row[0] for row in await cursor.fetchall()]

        inserted = 0
        for menu_id in menu_ids:
            for size_data in default_sizes:
                # Проверяем существование
                cursor = await db.execute(
                    "SELECT 1 FROM menu_item_sizes WHERE menu_item_id = ? AND size = ?",
                    (menu_id, size_data["size"])
                )
                if await cursor.fetchone():
                    continue

                await db.execute(
                    """INSERT INTO menu_item_sizes (menu_item_id, size, size_name, price_diff)
                       VALUES (?, ?, ?, ?)""",
                    (menu_id, size_data["size"], size_data["size_name"], size_data["price_diff"])
                )
                inserted += 1

        await db.commit()

        logger.info(
            "default_sizes_initialized",
            extra={"menu_items": len(menu_ids), "sizes_inserted": inserted}
        )


# ===== MODIFIERS =====

async def get_modifiers(category: str | None = None) -> list[dict]:
    """
    Получить модификаторы, опционально по категории.
    Returns: [{"id": 1, "name": "Ванильный сироп", "category": "syrup", "price": 50}, ...]
    """
    async with aiosqlite.connect(DB_PATH) as db:
        if category is not None:
            cursor = await db.execute(
                """SELECT id, name, category, price
                   FROM modifiers
                   WHERE is_available = 1 AND category = ?
                   ORDER BY sort_order, name""",
                (category,)
            )
        else:
            cursor = await db.execute(
                """SELECT id, name, category, price
                   FROM modifiers
                   WHERE is_available = 1
                   ORDER BY category, sort_order, name"""
            )
        rows = await cursor.fetchall()
        return [
            {"id": r[0], "name": r[1], "category": r[2], "price": r[3]}
            for r in rows
        ]


async def get_menu_item_modifiers(menu_item_id: int) -> list[dict]:
    """
    Получить доступные модификаторы для позиции меню.
    Returns: [{"id": 1, "name": "Ванильный сироп", "category": "syrup", "price": 50}, ...]
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """SELECT m.id, m.name, m.category, m.price
               FROM modifiers m
               JOIN menu_item_modifiers mim ON m.id = mim.modifier_id
               WHERE mim.menu_item_id = ? AND m.is_available = 1
               ORDER BY m.category, m.sort_order, m.name""",
            (menu_item_id,)
        )
        rows = await cursor.fetchall()
        return [
            {"id": r[0], "name": r[1], "category": r[2], "price": r[3]}
            for r in rows
        ]


async def get_available_modifiers(menu_item_id: int | None = None) -> list[dict]:
    """
    Возвращает доступные модификаторы.
    Если menu_item_id указан — только для этой позиции (из menu_item_modifiers).
    Если нет — все доступные модификаторы.
    Returns: [{"id": 1, "name": "Ванильный сироп", "category": "syrup", "price": 50}, ...]
    """
    async with aiosqlite.connect(DB_PATH) as db:
        if menu_item_id is not None:
            cursor = await db.execute(
                """SELECT m.id, m.name, m.category, m.price
                   FROM modifiers m
                   JOIN menu_item_modifiers mim ON m.id = mim.modifier_id
                   WHERE mim.menu_item_id = ? AND m.is_available = 1
                   ORDER BY m.category, m.sort_order, m.name""",
                (menu_item_id,)
            )
        else:
            cursor = await db.execute(
                """SELECT id, name, category, price
                   FROM modifiers
                   WHERE is_available = 1
                   ORDER BY category, sort_order, name"""
            )
        rows = await cursor.fetchall()
        return [
            {"id": r[0], "name": r[1], "category": r[2], "price": r[3]}
            for r in rows
        ]


async def get_modifiers_by_ids(modifier_ids: list[int]) -> list[dict]:
    """
    Возвращает модификаторы по списку ID.
    Returns: [{"id": 1, "name": "Ванильный сироп", "category": "syrup", "price": 50}, ...]
    """
    if not modifier_ids:
        return []

    async with aiosqlite.connect(DB_PATH) as db:
        placeholders = ",".join("?" * len(modifier_ids))
        cursor = await db.execute(
            f"""SELECT id, name, category, price
                FROM modifiers
                WHERE id IN ({placeholders})
                ORDER BY category, name""",
            modifier_ids
        )
        rows = await cursor.fetchall()
        return [
            {"id": r[0], "name": r[1], "category": r[2], "price": r[3]}
            for r in rows
        ]


async def init_modifiers() -> None:
    """
    Инициализирует модификаторы из data/modifiers.json.
    Связывает все модификаторы со всеми позициями меню.
    Idempotent: не дублирует существующие записи.
    """
    if not MODIFIERS_JSON.exists():
        logger.warning("modifiers_json_not_found", extra={"path": str(MODIFIERS_JSON)})
        return

    with open(MODIFIERS_JSON, encoding="utf-8") as f:
        data = json.load(f)

    modifiers_list = data.get("modifiers", [])
    if not modifiers_list:
        logger.info("no_modifiers_in_json")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        # Вставляем модификаторы
        inserted_modifiers = 0
        modifier_ids: list[int] = []

        for mod_data in modifiers_list:
            # Проверяем существование по имени
            cursor = await db.execute(
                "SELECT id FROM modifiers WHERE name = ?",
                (mod_data["name"],)
            )
            row = await cursor.fetchone()
            if row and row[0] is not None:
                modifier_ids.append(row[0])
                continue

            cursor = await db.execute(
                """INSERT INTO modifiers (name, category, price)
                   VALUES (?, ?, ?)""",
                (mod_data["name"], mod_data["category"], mod_data["price"])
            )
            if cursor.lastrowid is not None:
                modifier_ids.append(cursor.lastrowid)
            inserted_modifiers += 1

        # Получаем все menu_items
        cursor = await db.execute("SELECT id FROM menu_items")
        menu_ids = [row[0] for row in await cursor.fetchall()]

        # Связываем модификаторы со всеми позициями
        linked = 0
        for menu_id in menu_ids:
            for modifier_id in modifier_ids:
                cursor = await db.execute(
                    "SELECT 1 FROM menu_item_modifiers WHERE menu_item_id = ? AND modifier_id = ?",
                    (menu_id, modifier_id)
                )
                if await cursor.fetchone():
                    continue

                await db.execute(
                    "INSERT INTO menu_item_modifiers (menu_item_id, modifier_id) VALUES (?, ?)",
                    (menu_id, modifier_id)
                )
                linked += 1

        await db.commit()

        logger.info(
            "modifiers_initialized",
            extra={
                "modifiers_inserted": inserted_modifiers,
                "total_modifiers": len(modifier_ids),
                "menu_items": len(menu_ids),
                "links_created": linked
            }
        )
