-- Размеры для позиций меню
CREATE TABLE IF NOT EXISTS menu_item_sizes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    menu_item_id INTEGER NOT NULL,
    size TEXT NOT NULL,           -- 'S', 'M', 'L'
    size_name TEXT NOT NULL,      -- 'Маленький 250мл', 'Средний 350мл', 'Большой 450мл'
    price_diff INTEGER DEFAULT 0, -- +0, +30, +50 к базовой цене
    available INTEGER DEFAULT 1,
    FOREIGN KEY (menu_item_id) REFERENCES menu_items(id)
);

-- Модификаторы (сиропы, молоко и т.д.)
CREATE TABLE IF NOT EXISTS modifiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,           -- 'Ванильный сироп'
    category TEXT NOT NULL,       -- 'syrup', 'milk', 'extra'
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
    item_index INTEGER NOT NULL,  -- индекс позиции в заказе
    modifier_id INTEGER NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(id),
    FOREIGN KEY (modifier_id) REFERENCES modifiers(id)
);

-- Индексы
CREATE INDEX IF NOT EXISTS idx_sizes_menu ON menu_item_sizes(menu_item_id);
CREATE INDEX IF NOT EXISTS idx_order_mods ON order_item_modifiers(order_id);
CREATE INDEX IF NOT EXISTS idx_modifiers_category ON modifiers(category);
