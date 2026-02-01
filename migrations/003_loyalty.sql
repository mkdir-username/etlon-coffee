-- Таблица лояльности пользователя
CREATE TABLE IF NOT EXISTS loyalty (
    user_id INTEGER PRIMARY KEY,
    points INTEGER DEFAULT 0,
    stamps INTEGER DEFAULT 0,
    total_orders INTEGER DEFAULT 0,
    total_spent INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- История операций с баллами
CREATE TABLE IF NOT EXISTS points_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,  -- положительное = начисление, отрицательное = списание
    operation TEXT NOT NULL,  -- 'accrual', 'redemption', 'refund'
    order_id INTEGER,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES loyalty(user_id)
);

CREATE INDEX IF NOT EXISTS idx_points_history_user ON points_history(user_id);
