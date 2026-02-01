"""
Инициализация базы данных Etlon Coffee.
Запустить один раз перед первым запуском бота:
    python init_db.py
"""
import json
import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).parent / "etlon.db"
MENU_JSON = Path(__file__).parent / "data" / "menu.json"
MODIFIERS_JSON = Path(__file__).parent / "data" / "modifiers.json"
MIGRATIONS_DIR = Path(__file__).parent / "migrations"

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


def load_menu_from_json() -> list[tuple[str, int]]:
    """Загрузка меню из data/menu.json"""
    with open(MENU_JSON, encoding="utf-8") as f:
        data = json.load(f)
    return [(item["name"], item["price"]) for item in data["items"]]


def apply_migrations(cursor: sqlite3.Cursor) -> None:
    """Применяет SQL-миграции из папки migrations/"""
    if not MIGRATIONS_DIR.exists():
        print(f"Папка миграций не найдена: {MIGRATIONS_DIR}")
        return

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        print("Миграции не найдены")
        return

    for migration_file in migration_files:
        print(f"Применяю миграцию: {migration_file.name}")
        sql = migration_file.read_text(encoding="utf-8")
        cursor.executescript(sql)


def load_modifiers(cursor: sqlite3.Cursor) -> None:
    """Загружает модификаторы из data/modifiers.json и связывает с позициями меню."""
    if not MODIFIERS_JSON.exists():
        print(f"Файл модификаторов не найден: {MODIFIERS_JSON}")
        return

    with open(MODIFIERS_JSON, encoding="utf-8") as f:
        data = json.load(f)

    modifiers_list = data.get("modifiers", [])
    if not modifiers_list:
        print("Модификаторы не найдены в JSON")
        return

    inserted = 0
    modifier_ids: list[int] = []

    for idx, mod_data in enumerate(modifiers_list):
        cursor.execute(
            "SELECT id FROM modifiers WHERE name = ?",
            (mod_data["name"],)
        )
        row = cursor.fetchone()
        if row:
            modifier_ids.append(row[0])
            continue

        cursor.execute(
            """INSERT INTO modifiers (name, category, price, sort_order)
               VALUES (?, ?, ?, ?)""",
            (mod_data["name"], mod_data["category"], mod_data["price"], idx)
        )
        modifier_ids.append(cursor.lastrowid)
        inserted += 1

    if inserted > 0:
        print(f"Добавлено {inserted} модификаторов из {MODIFIERS_JSON}")
    else:
        print("Модификаторы уже загружены, пропускаю")

    # Связываем модификаторы со всеми позициями меню
    cursor.execute("SELECT id FROM menu_items")
    menu_ids = [row[0] for row in cursor.fetchall()]

    linked = 0
    for menu_id in menu_ids:
        for modifier_id in modifier_ids:
            cursor.execute(
                "SELECT 1 FROM menu_item_modifiers WHERE menu_item_id = ? AND modifier_id = ?",
                (menu_id, modifier_id)
            )
            if cursor.fetchone():
                continue

            cursor.execute(
                "INSERT INTO menu_item_modifiers (menu_item_id, modifier_id) VALUES (?, ?)",
                (menu_id, modifier_id)
            )
            linked += 1

    if linked > 0:
        print(f"Создано {linked} связей модификаторов с позициями меню")


def load_sizes(cursor: sqlite3.Cursor) -> None:
    """Загружает размеры по умолчанию из data/modifiers.json."""
    if not MODIFIERS_JSON.exists():
        return

    with open(MODIFIERS_JSON, encoding="utf-8") as f:
        data = json.load(f)

    default_sizes = data.get("sizes", {}).get("default", [])
    if not default_sizes:
        return

    cursor.execute("SELECT id FROM menu_items")
    menu_ids = [row[0] for row in cursor.fetchall()]

    inserted = 0
    for menu_id in menu_ids:
        for size_data in default_sizes:
            cursor.execute(
                "SELECT 1 FROM menu_item_sizes WHERE menu_item_id = ? AND size = ?",
                (menu_id, size_data["size"])
            )
            if cursor.fetchone():
                continue

            cursor.execute(
                """INSERT INTO menu_item_sizes (menu_item_id, size, size_name, price_diff)
                   VALUES (?, ?, ?, ?)""",
                (menu_id, size_data["size"], size_data["size_name"], size_data["price_diff"])
            )
            inserted += 1

    if inserted > 0:
        print(f"Создано {inserted} записей размеров для позиций меню")


def init_database() -> None:
    db = sqlite3.connect(DB_PATH)
    cursor = db.cursor()

    cursor.executescript(SCHEMA)

    cursor.execute("SELECT COUNT(*) FROM menu_items")
    if cursor.fetchone()[0] == 0:
        menu_items = load_menu_from_json()
        cursor.executemany(
            "INSERT INTO menu_items (name, price) VALUES (?, ?)",
            menu_items
        )
        print(f"Добавлено {len(menu_items)} позиций из {MENU_JSON}")
    else:
        print("Меню уже заполнено, пропускаю")

    apply_migrations(cursor)

    load_modifiers(cursor)
    load_sizes(cursor)

    db.commit()
    db.close()
    print(f"База данных: {DB_PATH}")


if __name__ == "__main__":
    init_database()
