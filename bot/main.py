import asyncio
import json
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import settings
from bot.database import ensure_tables, init_default_sizes, init_modifiers
from bot.handlers import client_router, barista_router


def setup_logging():
    """Настройка логирования для ИИ-агента: JSON в prod, text в dev"""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    if settings.log_format == "json":
        class JsonFormatter(logging.Formatter):
            def format(self, record):
                log_obj = {
                    "timestamp": self.formatTime(record, "%H:%M:%S"),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                }
                # Structured context
                for attr in ("user_id", "order_id", "state", "item_id", "action"):
                    if hasattr(record, attr):
                        log_obj[attr] = getattr(record, attr)
                if record.exc_info:
                    log_obj["exception"] = self.formatException(record.exc_info)
                return json.dumps(log_obj, ensure_ascii=False)
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S"
        )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # aiogram шумит на DEBUG
    logging.getLogger("aiogram").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def main() -> None:
    settings.check_required()
    setup_logging()
    await ensure_tables()
    await init_default_sizes()
    await init_modifiers()

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(client_router)
    dp.include_router(barista_router)

    logger.info("Etlon Coffee Bot запущен")

    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
