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

    db.commit()
    db.close()
    print(f"База данных: {DB_PATH}")


if __name__ == "__main__":
    init_database()
