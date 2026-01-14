#!/usr/bin/env python3
"""
Точка входа для запуска бота Etlon Coffee.

Перед первым запуском:
    1. Скопируй .env.example в .env
    2. Заполни BOT_TOKEN и BARISTA_IDS
    3. Запусти: python init_db.py
    4. Запусти: python run.py
"""
import asyncio
from bot.main import main


if __name__ == "__main__":
    asyncio.run(main())
