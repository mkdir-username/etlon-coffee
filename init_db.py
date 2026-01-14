"""
Инициализация базы данных Etlon Coffee.
Запустить один раз перед первым запуском бота:
    python init_db.py
"""
import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).parent / "etlon.db"

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

# Стандартное меню кофейни
MENU_ITEMS = [
    ("Эспрессо", 150),
    ("Американо", 180),
    ("Капучино", 250),
    ("Латте", 280),
    ("Флэт Уайт", 300),
    ("Раф", 320),
    ("Какао", 220),
    ("Чай чёрный", 150),
    ("Чай зелёный", 150),
    ("Круассан", 180),
]


def init_database() -> None:
    db = sqlite3.connect(DB_PATH)
    cursor = db.cursor()

    # Создаём таблицы
    cursor.executescript(SCHEMA)

    # Проверяем, есть ли уже меню
    cursor.execute("SELECT COUNT(*) FROM menu_items")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            "INSERT INTO menu_items (name, price) VALUES (?, ?)",
            MENU_ITEMS
        )
        print(f"Добавлено {len(MENU_ITEMS)} позиций в меню")
    else:
        print("Меню уже заполнено, пропускаю")

    db.commit()
    db.close()
    print(f"База данных создана: {DB_PATH}")


if __name__ == "__main__":
    init_database()
