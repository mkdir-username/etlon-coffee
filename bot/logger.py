"""Модуль структурированного логирования для Etlon Coffee Bot."""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_TO_FILE = os.getenv("LOG_TO_FILE", "true").lower() == "true"
LOG_TO_CONSOLE = os.getenv("LOG_TO_CONSOLE", "true").lower() == "true"
LOG_DIR = Path(__file__).parent.parent / "logs"


class BotFormatter(logging.Formatter):
    """Форматтер для структурированных логов бота."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        level = record.levelname

        user_part = ""
        if hasattr(record, "user_id") and record.user_id is not None:
            user_part = f" [USER:{record.user_id}]"

        action_part = ""
        if hasattr(record, "action") and record.action:
            action_part = f" [{record.action}]"

        context_part = ""
        if hasattr(record, "context") and record.context:
            ctx = record.context
            if isinstance(ctx, dict):
                pairs = [f'{k}={repr(v) if isinstance(v, str) else v}' for k, v in ctx.items()]
                context_part = " {" + ", ".join(pairs) + "}"

        message = record.getMessage()
        return f"[{timestamp}] [{level}]{user_part}{action_part} {message}{context_part}"


class BotLogger:
    """
    Структурированный логгер для бота.

    Использование:
        from bot.logger import log
        log.user_action(123, "CART_ADD", item_id=5, name="Латте")
        log.fsm_transition(123, "browsing_menu", "selecting_size", "menu:5")
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("etlon_coffee_bot")
        self._setup_logging()

    def _setup_logging(self) -> None:
        """Настраивает handlers и formatters."""
        self._logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
        self._logger.handlers.clear()

        formatter = BotFormatter()

        if LOG_TO_CONSOLE:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.DEBUG)
            console_handler.setFormatter(formatter)
            self._logger.addHandler(console_handler)

        if LOG_TO_FILE:
            LOG_DIR.mkdir(parents=True, exist_ok=True)

            # bot.log — все логи
            main_handler = logging.FileHandler(LOG_DIR / "bot.log", encoding="utf-8")
            main_handler.setLevel(logging.DEBUG)
            main_handler.setFormatter(formatter)
            self._logger.addHandler(main_handler)

            # errors.log — ERROR+
            error_handler = logging.FileHandler(LOG_DIR / "errors.log", encoding="utf-8")
            error_handler.setLevel(logging.ERROR)
            error_handler.setFormatter(formatter)
            self._logger.addHandler(error_handler)

            # debug.log — только если LOG_LEVEL=DEBUG
            if LOG_LEVEL == "DEBUG":
                debug_handler = logging.FileHandler(LOG_DIR / "debug.log", encoding="utf-8")
                debug_handler.setLevel(logging.DEBUG)
                debug_handler.setFormatter(formatter)
                self._logger.addHandler(debug_handler)

    def _log(
        self,
        level: int,
        message: str,
        user_id: int | None = None,
        action: str | None = None,
        **context: Any,
    ) -> None:
        """Базовый метод логирования с контекстом."""
        extra = {
            "user_id": user_id,
            "action": action,
            "context": context if context else None,
        }
        self._logger.log(level, message, extra=extra)

    def user_action(self, user_id: int, action: str, **context: Any) -> None:
        """
        Логирует действие пользователя.

        Примеры:
            log.user_action(123, "CART_ADD", item_id=5, name="Латте", price=220)
            log.user_action(123, "ORDER_CREATED", order_id=456, total=500)
        """
        messages = {
            "CART_ADD": "Добавлено в корзину",
            "CART_REMOVE": "Удалено из корзины",
            "CART_INC": "Увеличено количество",
            "CART_DEC": "Уменьшено количество",
            "CART_CLEAR": "Корзина очищена",
            "ORDER_CREATED": "Заказ создан",
            "ORDER_CONFIRMED": "Заказ подтверждён",
            "ORDER_CANCELLED": "Заказ отменён",
            "TIME_SELECTED": "Выбрано время забора",
            "MENU_VIEW": "Просмотр меню",
            "START": "Пользователь запустил бота",
        }
        msg = messages.get(action, action)
        self._log(logging.INFO, msg, user_id=user_id, action=action, **context)

    def fsm_transition(
        self,
        user_id: int,
        from_state: str,
        to_state: str,
        trigger: str,
    ) -> None:
        """
        Логирует переход FSM.

        Пример:
            log.fsm_transition(123, "browsing_menu", "selecting_size", "menu:5")
        """
        from_str = from_state or "None"
        to_str = to_state or "None"
        msg = f"{from_str} → {to_str} (trigger: {trigger})"
        self._log(logging.DEBUG, msg, user_id=user_id, action="FSM")

    def db_operation(self, operation: str, table: str, **params: Any) -> None:
        """
        Логирует операцию с БД.

        Пример:
            log.db_operation("INSERT", "favorites", user_id=123, item_id=5)
        """
        msg = f"{operation} {table}"
        self._log(logging.INFO, msg, action="DB", **params)

    def callback_received(
        self,
        user_id: int,
        callback_data: str,
        handler: str,
    ) -> None:
        """
        Логирует входящий callback.

        Пример:
            log.callback_received(123, "menu:5", "add_to_cart")
        """
        msg = f"Callback: {callback_data}"
        self._log(
            logging.DEBUG,
            msg,
            user_id=user_id,
            action="CALLBACK",
            handler=handler,
        )

    def error(
        self,
        user_id: int | None,
        action: str,
        error: Exception,
        **context: Any,
    ) -> None:
        """
        Логирует ошибку с полным контекстом.

        Пример:
            log.error(123, "cancel_order", exc, order_id=456)
        """
        error_name = type(error).__name__
        msg = f"{error_name}: {error}"
        self._log(logging.ERROR, msg, user_id=user_id, action=action, **context)

    def command(self, user_id: int, command: str) -> None:
        """
        Логирует команду.

        Пример:
            log.command(123, "/start")
        """
        msg = f"Команда: {command}"
        self._log(logging.INFO, msg, user_id=user_id, action="COMMAND")

    def barista_action(self, user_id: int, action: str, **context: Any) -> None:
        """
        Логирует действие баристы.

        Пример:
            log.barista_action(123, "STATUS_CHANGE", order_id=456, new_status="PREPARING")
        """
        messages = {
            "STATUS_CHANGE": "Статус заказа изменён",
            "ORDER_VIEW": "Просмотр заказа",
            "PANEL_OPEN": "Открыта панель баристы",
        }
        msg = messages.get(action, action)
        self._log(logging.INFO, msg, user_id=user_id, action=f"BARISTA:{action}", **context)

    def debug(self, message: str, user_id: int | None = None, **context: Any) -> None:
        """
        Логирует отладочное сообщение.

        Пример:
            log.debug("Проверка состояния", user_id=123, state="browsing_menu")
        """
        self._log(logging.DEBUG, message, user_id=user_id, **context)

    def info(self, message: str, user_id: int | None = None, **context: Any) -> None:
        """
        Логирует информационное сообщение.

        Пример:
            log.info("Бот запущен", version="1.0.0")
        """
        self._log(logging.INFO, message, user_id=user_id, **context)

    def warning(self, message: str, user_id: int | None = None, **context: Any) -> None:
        """
        Логирует предупреждение.

        Пример:
            log.warning("Низкий остаток", item_id=5, remaining=2)
        """
        self._log(logging.WARNING, message, user_id=user_id, **context)


log = BotLogger()
