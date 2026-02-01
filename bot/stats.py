"""Модуль статистики для баристы."""
import json
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import aiosqlite

from bot.database import DB_PATH
from bot.models import OrderStatus

logger = logging.getLogger(__name__)


@dataclass
class DailyStats:
    target_date: date
    total_orders: int
    completed_orders: int
    cancelled_orders: int
    total_revenue: int
    avg_order_value: int
    popular_items: list[tuple[str, int]]  # (name, count)
    hourly_distribution: dict[int, int]  # hour -> count


@dataclass
class WeeklyStats:
    start_date: date
    end_date: date
    total_orders: int
    total_revenue: int
    avg_order_value: int
    daily_orders: dict[str, int]  # weekday name -> count


async def get_daily_stats(target_date: date) -> DailyStats:
    """
    Получить статистику за день.

    Returns:
        DailyStats с полной информацией о заказах за день
    """
    date_str = target_date.isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        # Количество заказов по статусам
        cursor = await db.execute(
            """
            SELECT status, COUNT(*) as cnt
            FROM orders
            WHERE date(created_at) = date(?)
            GROUP BY status
            """,
            (date_str,)
        )
        status_counts = dict(await cursor.fetchall())

        total_orders = sum(status_counts.values())
        completed_orders = status_counts.get(OrderStatus.COMPLETED.value, 0)
        cancelled_orders = status_counts.get(OrderStatus.CANCELLED.value, 0)

        # Выручка — только выполненные заказы
        cursor = await db.execute(
            """
            SELECT COALESCE(SUM(total), 0)
            FROM orders
            WHERE date(created_at) = date(?)
              AND status = ?
            """,
            (date_str, OrderStatus.COMPLETED.value)
        )
        row = await cursor.fetchone()
        total_revenue = row[0] if row else 0

        # Средний чек
        avg_order_value = total_revenue // completed_orders if completed_orders > 0 else 0

        # Популярные позиции — парсим JSON items из всех заказов за день
        cursor = await db.execute(
            """
            SELECT items
            FROM orders
            WHERE date(created_at) = date(?)
              AND status != ?
            """,
            (date_str, OrderStatus.CANCELLED.value)
        )
        rows = await cursor.fetchall()

        item_counter: Counter[str] = Counter()
        for (items_json,) in rows:
            try:
                items = json.loads(items_json)
                for item in items:
                    name = item.get("name", "")
                    quantity = item.get("quantity", 1)
                    if name:
                        item_counter[name] += quantity
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("parse_items_failed", extra={"items": items_json, "error": str(e)})

        popular_items = item_counter.most_common(3)

        # Распределение по часам
        cursor = await db.execute(
            """
            SELECT strftime('%H', created_at) as hour, COUNT(*) as cnt
            FROM orders
            WHERE date(created_at) = date(?)
              AND status != ?
            GROUP BY hour
            ORDER BY cnt DESC
            """,
            (date_str, OrderStatus.CANCELLED.value)
        )
        hourly_rows = await cursor.fetchall()
        hourly_distribution = {int(h): cnt for h, cnt in hourly_rows}

    logger.info(
        "daily_stats_fetched",
        extra={
            "date": date_str,
            "total": total_orders,
            "completed": completed_orders,
            "revenue": total_revenue
        }
    )

    return DailyStats(
        target_date=target_date,
        total_orders=total_orders,
        completed_orders=completed_orders,
        cancelled_orders=cancelled_orders,
        total_revenue=total_revenue,
        avg_order_value=avg_order_value,
        popular_items=popular_items,
        hourly_distribution=hourly_distribution,
    )


async def get_weekly_stats(days: int = 7) -> WeeklyStats:
    """
    Сравнение с предыдущим периодом.

    Args:
        days: количество дней для анализа (по умолчанию 7)

    Returns:
        WeeklyStats со сводной информацией за период
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)
    start_str = start_date.isoformat()
    end_str = end_date.isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        # Общее количество заказов и выручка
        cursor = await db.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(total), 0)
            FROM orders
            WHERE date(created_at) BETWEEN date(?) AND date(?)
              AND status = ?
            """,
            (start_str, end_str, OrderStatus.COMPLETED.value)
        )
        row = await cursor.fetchone()
        completed_orders = row[0] if row else 0
        total_revenue = row[1] if row else 0

        # Всего заказов (включая отмененные)
        cursor = await db.execute(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE date(created_at) BETWEEN date(?) AND date(?)
            """,
            (start_str, end_str)
        )
        row = await cursor.fetchone()
        total_orders = row[0] if row else 0

        # Средний чек
        avg_order_value = total_revenue // completed_orders if completed_orders > 0 else 0

        # Распределение по дням недели
        cursor = await db.execute(
            """
            SELECT strftime('%w', created_at) as weekday, COUNT(*) as cnt
            FROM orders
            WHERE date(created_at) BETWEEN date(?) AND date(?)
              AND status != ?
            GROUP BY weekday
            ORDER BY weekday
            """,
            (start_str, end_str, OrderStatus.CANCELLED.value)
        )
        weekday_rows = await cursor.fetchall()

        # %w: 0=воскресенье, 1=понедельник, ..., 6=суббота
        weekday_names = ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"]
        daily_orders = {weekday_names[int(wd)]: cnt for wd, cnt in weekday_rows}

    logger.info(
        "weekly_stats_fetched",
        extra={
            "start": start_str,
            "end": end_str,
            "total": total_orders,
            "revenue": total_revenue
        }
    )

    return WeeklyStats(
        start_date=start_date,
        end_date=end_date,
        total_orders=total_orders,
        total_revenue=total_revenue,
        avg_order_value=avg_order_value,
        daily_orders=daily_orders,
    )


def format_stats(stats: DailyStats) -> str:
    """Форматирует дневную статистику для отправки в Telegram"""
    date_formatted = stats.target_date.strftime("%d.%m.%Y")

    if stats.total_orders == 0:
        return f"📊 Статистика за {date_formatted}\n\nЗаказов не было"

    lines = [
        f"📊 Статистика за {date_formatted}",
        "",
        f"📦 Заказов: {stats.total_orders}",
        f"✅ Выполнено: {stats.completed_orders}",
        f"❌ Отменено: {stats.cancelled_orders}",
        "",
        f"💰 Выручка: {stats.total_revenue:,}₽".replace(",", " "),
        f"📈 Средний чек: {stats.avg_order_value:,}₽".replace(",", " "),
    ]

    if stats.popular_items:
        lines.append("")
        lines.append("🏆 Топ позиций:")
        for i, (name, count) in enumerate(stats.popular_items, 1):
            lines.append(f"{i}. {name} — {count} шт")

    if stats.hourly_distribution:
        # Топ-2 пиковых часа
        top_hours = sorted(
            stats.hourly_distribution.items(),
            key=lambda x: x[1],
            reverse=True
        )[:2]
        if top_hours:
            lines.append("")
            lines.append("⏰ Пиковые часы:")
            for hour, count in top_hours:
                lines.append(f"• {hour:02d}:00-{hour + 1:02d}:00 — {count} заказов")

    return "\n".join(lines)


def format_weekly_stats(stats: WeeklyStats) -> str:
    """Форматирует недельную статистику для отправки в Telegram"""
    if stats.total_orders == 0:
        return "📊 За последние 7 дней\n\nЗаказов не было"

    lines = [
        "📊 За последние 7 дней",
        "",
        f"📦 Заказов: {stats.total_orders}",
        f"💰 Выручка: {stats.total_revenue:,}₽".replace(",", " "),
        f"📈 Средний чек: {stats.avg_order_value:,}₽".replace(",", " "),
    ]

    if stats.daily_orders:
        lines.append("")
        lines.append("📅 По дням:")
        # Сортируем в правильном порядке: Пн, Вт, ..., Вс
        weekday_order = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        day_values = [f"{wd}: {stats.daily_orders.get(wd, 0)}" for wd in weekday_order]
        # Разбиваем на две строки для читаемости
        lines.append(" | ".join(day_values[:3]))
        lines.append(" | ".join(day_values[3:]))

    return "\n".join(lines)
