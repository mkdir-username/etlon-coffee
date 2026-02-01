#!/usr/bin/env python3
"""
Точка входа для запуска бота Etlon Coffee.

Запуск: source venv/bin/activate && python run.py
"""
import os
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
PID_FILE = ROOT / ".bot.pid"


def check_venv() -> None:
    """Проверяет что venv активирован."""
    try:
        import aiogram  # noqa: F401
    except ImportError:
        sys.exit(
            "❌ aiogram не найден.\n"
            "   Запусти: source venv/bin/activate && python run.py"
        )


def kill_previous_instance() -> None:
    """Убивает предыдущий инстанс бота если он запущен."""
    if not PID_FILE.exists():
        return

    try:
        old_pid = int(PID_FILE.read_text().strip())
        if old_pid == os.getpid():
            return

        os.kill(old_pid, signal.SIGTERM)
        print(f"Остановлен предыдущий инстанс (PID {old_pid})")

        for _ in range(30):
            try:
                os.kill(old_pid, 0)
                time.sleep(0.1)
            except OSError:
                break
    except (ValueError, OSError, ProcessLookupError):
        pass
    finally:
        PID_FILE.unlink(missing_ok=True)


def write_pid() -> None:
    """Записывает текущий PID в файл."""
    PID_FILE.write_text(str(os.getpid()))


def cleanup_pid() -> None:
    """Удаляет PID-файл при завершении."""
    PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    import asyncio

    check_venv()
    kill_previous_instance()
    write_pid()

    try:
        from bot.main import main
        asyncio.run(main())
    finally:
        cleanup_pid()
