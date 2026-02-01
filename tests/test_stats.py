"""Unit-тесты для модуля bot/stats.py."""
from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest

from bot.stats import (
    DailyStats,
    WeeklyStats,
    format_stats,
    format_weekly_stats,
    get_daily_stats,
    get_weekly_stats,
)
from tests.conftest import insert_order


class TestGetDailyStats:
    """Тесты для get_daily_stats."""

    @pytest.mark.asyncio
    async def test_пустой_день_возвращает_нулевую_статистику(self, test_db):
        """Если нет заказов за день — все показатели нулевые."""
        target = date(2026, 2, 1)

        with patch("bot.stats.DB_PATH", test_db):
            stats = await get_daily_stats(target)

        assert isinstance(stats, DailyStats)
        assert stats.target_date == target
        assert stats.total_orders == 0
        assert stats.completed_orders == 0
        assert stats.cancelled_orders == 0
        assert stats.total_revenue == 0
        assert stats.avg_order_value == 0
        assert stats.popular_items == []
        assert stats.hourly_distribution == {}

    @pytest.mark.asyncio
    async def test_день_с_заказами_подсчитывает_статусы(self, test_db):
        """Проверяем подсчёт заказов по статусам: completed, cancelled, preparing."""
        target = date(2026, 2, 1)

        # 2 completed, 1 cancelled, 1 preparing
        await insert_order(
            test_db,
            user_id=100,
            user_name="User1",
            items=[{"name": "Латте", "price": 220, "quantity": 1}],
            total=220,
            status="completed",
            created_at=datetime(2026, 2, 1, 9, 0, 0),
        )
        await insert_order(
            test_db,
            user_id=101,
            user_name="User2",
            items=[{"name": "Капучино", "price": 200, "quantity": 1}],
            total=200,
            status="completed",
            created_at=datetime(2026, 2, 1, 10, 0, 0),
        )
        await insert_order(
            test_db,
            user_id=102,
            user_name="User3",
            items=[{"name": "Раф", "price": 280, "quantity": 1}],
            total=280,
            status="cancelled",
            created_at=datetime(2026, 2, 1, 11, 0, 0),
        )
        await insert_order(
            test_db,
            user_id=103,
            user_name="User4",
            items=[{"name": "Эспрессо", "price": 120, "quantity": 1}],
            total=120,
            status="preparing",
            created_at=datetime(2026, 2, 1, 12, 0, 0),
        )

        with patch("bot.stats.DB_PATH", test_db):
            stats = await get_daily_stats(target)

        assert stats.total_orders == 4
        assert stats.completed_orders == 2
        assert stats.cancelled_orders == 1

    @pytest.mark.asyncio
    async def test_выручка_считается_только_по_completed(self, test_db):
        """Выручка включает только выполненные заказы."""
        target = date(2026, 2, 1)

        await insert_order(
            test_db,
            user_id=100,
            user_name="User1",
            items=[{"name": "Латте", "price": 220, "quantity": 1}],
            total=220,
            status="completed",
            created_at=datetime(2026, 2, 1, 9, 0, 0),
        )
        await insert_order(
            test_db,
            user_id=101,
            user_name="User2",
            items=[{"name": "Капучино", "price": 200, "quantity": 1}],
            total=200,
            status="completed",
            created_at=datetime(2026, 2, 1, 10, 0, 0),
        )
        # Отменённый — не считается в выручку
        await insert_order(
            test_db,
            user_id=102,
            user_name="User3",
            items=[{"name": "Раф", "price": 280, "quantity": 1}],
            total=280,
            status="cancelled",
            created_at=datetime(2026, 2, 1, 11, 0, 0),
        )

        with patch("bot.stats.DB_PATH", test_db):
            stats = await get_daily_stats(target)

        assert stats.total_revenue == 420  # 220 + 200
        assert stats.avg_order_value == 210  # 420 / 2

    @pytest.mark.asyncio
    async def test_средний_чек_при_отсутствии_completed(self, test_db):
        """Средний чек = 0 если нет выполненных заказов."""
        target = date(2026, 2, 1)

        await insert_order(
            test_db,
            user_id=100,
            user_name="User1",
            items=[{"name": "Латте", "price": 220, "quantity": 1}],
            total=220,
            status="cancelled",
            created_at=datetime(2026, 2, 1, 9, 0, 0),
        )

        with patch("bot.stats.DB_PATH", test_db):
            stats = await get_daily_stats(target)

        assert stats.completed_orders == 0
        assert stats.total_revenue == 0
        assert stats.avg_order_value == 0

    @pytest.mark.asyncio
    async def test_popular_items_топ_3_по_quantity(self, test_db):
        """Популярные позиции — топ-3 по суммарному количеству."""
        target = date(2026, 2, 1)

        # Латте — 5 шт (топ-1)
        await insert_order(
            test_db,
            user_id=100,
            user_name="User1",
            items=[{"name": "Латте", "price": 220, "quantity": 3}],
            total=660,
            status="completed",
            created_at=datetime(2026, 2, 1, 9, 0, 0),
        )
        await insert_order(
            test_db,
            user_id=101,
            user_name="User2",
            items=[{"name": "Латте", "price": 220, "quantity": 2}],
            total=440,
            status="preparing",
            created_at=datetime(2026, 2, 1, 10, 0, 0),
        )
        # Капучино — 3 шт (топ-2)
        await insert_order(
            test_db,
            user_id=102,
            user_name="User3",
            items=[{"name": "Капучино", "price": 200, "quantity": 3}],
            total=600,
            status="completed",
            created_at=datetime(2026, 2, 1, 11, 0, 0),
        )
        # Эспрессо — 2 шт (топ-3)
        await insert_order(
            test_db,
            user_id=103,
            user_name="User4",
            items=[{"name": "Эспрессо", "price": 120, "quantity": 2}],
            total=240,
            status="confirmed",
            created_at=datetime(2026, 2, 1, 12, 0, 0),
        )
        # Раф — 1 шт (не попадёт в топ-3)
        await insert_order(
            test_db,
            user_id=104,
            user_name="User5",
            items=[{"name": "Раф", "price": 280, "quantity": 1}],
            total=280,
            status="completed",
            created_at=datetime(2026, 2, 1, 13, 0, 0),
        )
        # Отменённый — не учитывается в popular_items
        await insert_order(
            test_db,
            user_id=105,
            user_name="User6",
            items=[{"name": "Американо", "price": 150, "quantity": 10}],
            total=1500,
            status="cancelled",
            created_at=datetime(2026, 2, 1, 14, 0, 0),
        )

        with patch("bot.stats.DB_PATH", test_db):
            stats = await get_daily_stats(target)

        assert len(stats.popular_items) == 3
        assert stats.popular_items[0] == ("Латте", 5)
        assert stats.popular_items[1] == ("Капучино", 3)
        assert stats.popular_items[2] == ("Эспрессо", 2)

    @pytest.mark.asyncio
    async def test_hourly_distribution_группировка_по_часам(self, test_db):
        """Распределение по часам учитывает только не-cancelled заказы."""
        target = date(2026, 2, 1)

        # 2 заказа в 9:xx
        await insert_order(
            test_db,
            user_id=100,
            user_name="User1",
            items=[{"name": "Латте", "price": 220, "quantity": 1}],
            total=220,
            status="completed",
            created_at=datetime(2026, 2, 1, 9, 15, 0),
        )
        await insert_order(
            test_db,
            user_id=101,
            user_name="User2",
            items=[{"name": "Капучино", "price": 200, "quantity": 1}],
            total=200,
            status="completed",
            created_at=datetime(2026, 2, 1, 9, 45, 0),
        )
        # 1 заказ в 10:xx
        await insert_order(
            test_db,
            user_id=102,
            user_name="User3",
            items=[{"name": "Эспрессо", "price": 120, "quantity": 1}],
            total=120,
            status="preparing",
            created_at=datetime(2026, 2, 1, 10, 30, 0),
        )
        # cancelled — не учитывается
        await insert_order(
            test_db,
            user_id=103,
            user_name="User4",
            items=[{"name": "Раф", "price": 280, "quantity": 1}],
            total=280,
            status="cancelled",
            created_at=datetime(2026, 2, 1, 11, 0, 0),
        )

        with patch("bot.stats.DB_PATH", test_db):
            stats = await get_daily_stats(target)

        assert stats.hourly_distribution[9] == 2
        assert stats.hourly_distribution[10] == 1
        assert 11 not in stats.hourly_distribution

    @pytest.mark.asyncio
    async def test_заказы_другой_даты_не_учитываются(self, test_db):
        """Заказы за другие дни не влияют на статистику."""
        target = date(2026, 2, 1)

        # Заказ за целевой день
        await insert_order(
            test_db,
            user_id=100,
            user_name="User1",
            items=[{"name": "Латте", "price": 220, "quantity": 1}],
            total=220,
            status="completed",
            created_at=datetime(2026, 2, 1, 9, 0, 0),
        )
        # Заказ за предыдущий день
        await insert_order(
            test_db,
            user_id=101,
            user_name="User2",
            items=[{"name": "Капучино", "price": 200, "quantity": 1}],
            total=200,
            status="completed",
            created_at=datetime(2026, 1, 31, 10, 0, 0),
        )
        # Заказ за следующий день
        await insert_order(
            test_db,
            user_id=102,
            user_name="User3",
            items=[{"name": "Раф", "price": 280, "quantity": 1}],
            total=280,
            status="completed",
            created_at=datetime(2026, 2, 2, 11, 0, 0),
        )

        with patch("bot.stats.DB_PATH", test_db):
            stats = await get_daily_stats(target)

        assert stats.total_orders == 1
        assert stats.total_revenue == 220


class TestGetWeeklyStats:
    """Тесты для get_weekly_stats."""

    @pytest.mark.asyncio
    async def test_пустой_период_возвращает_нулевую_статистику(self, test_db):
        """Если нет заказов за период — все показатели нулевые."""
        with patch("bot.stats.DB_PATH", test_db), \
             patch("bot.stats.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 7)
            mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

            stats = await get_weekly_stats(days=7)

        assert isinstance(stats, WeeklyStats)
        assert stats.total_orders == 0
        assert stats.total_revenue == 0
        assert stats.avg_order_value == 0
        assert stats.daily_orders == {}

    @pytest.mark.asyncio
    async def test_период_с_заказами_подсчитывает_метрики(self, test_db):
        """Проверяем подсчёт total_orders, revenue, avg_order_value."""
        # Заказы в пределах недели (1-7 февраля 2026)
        await insert_order(
            test_db,
            user_id=100,
            user_name="User1",
            items=[{"name": "Латте", "price": 220, "quantity": 1}],
            total=220,
            status="completed",
            created_at=datetime(2026, 2, 2, 9, 0, 0),  # Пн
        )
        await insert_order(
            test_db,
            user_id=101,
            user_name="User2",
            items=[{"name": "Капучино", "price": 200, "quantity": 1}],
            total=200,
            status="completed",
            created_at=datetime(2026, 2, 3, 10, 0, 0),  # Вт
        )
        await insert_order(
            test_db,
            user_id=102,
            user_name="User3",
            items=[{"name": "Раф", "price": 280, "quantity": 1}],
            total=280,
            status="cancelled",
            created_at=datetime(2026, 2, 4, 11, 0, 0),  # Ср
        )

        with patch("bot.stats.DB_PATH", test_db), \
             patch("bot.stats.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 7)
            mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

            stats = await get_weekly_stats(days=7)

        assert stats.total_orders == 3  # всего
        assert stats.total_revenue == 420  # 220 + 200 (только completed)
        assert stats.avg_order_value == 210  # 420 / 2

    @pytest.mark.asyncio
    async def test_daily_orders_группировка_по_дням_недели(self, test_db):
        """Проверяем группировку заказов по дням недели."""
        # 2 февраля 2026 — понедельник
        await insert_order(
            test_db,
            user_id=100,
            user_name="User1",
            items=[{"name": "Латте", "price": 220, "quantity": 1}],
            total=220,
            status="completed",
            created_at=datetime(2026, 2, 2, 9, 0, 0),  # Пн
        )
        await insert_order(
            test_db,
            user_id=101,
            user_name="User2",
            items=[{"name": "Капучино", "price": 200, "quantity": 1}],
            total=200,
            status="completed",
            created_at=datetime(2026, 2, 2, 10, 0, 0),  # Пн
        )
        # 3 февраля 2026 — вторник
        await insert_order(
            test_db,
            user_id=102,
            user_name="User3",
            items=[{"name": "Эспрессо", "price": 120, "quantity": 1}],
            total=120,
            status="completed",
            created_at=datetime(2026, 2, 3, 11, 0, 0),  # Вт
        )
        # cancelled — не учитывается в daily_orders
        await insert_order(
            test_db,
            user_id=103,
            user_name="User4",
            items=[{"name": "Раф", "price": 280, "quantity": 1}],
            total=280,
            status="cancelled",
            created_at=datetime(2026, 2, 4, 12, 0, 0),  # Ср
        )

        with patch("bot.stats.DB_PATH", test_db), \
             patch("bot.stats.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 7)
            mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

            stats = await get_weekly_stats(days=7)

        assert stats.daily_orders.get("Пн") == 2
        assert stats.daily_orders.get("Вт") == 1
        assert "Ср" not in stats.daily_orders  # cancelled не считается

    @pytest.mark.asyncio
    async def test_заказы_вне_периода_не_учитываются(self, test_db):
        """Заказы за пределами периода не влияют на статистику."""
        # Внутри периода
        await insert_order(
            test_db,
            user_id=100,
            user_name="User1",
            items=[{"name": "Латте", "price": 220, "quantity": 1}],
            total=220,
            status="completed",
            created_at=datetime(2026, 2, 5, 9, 0, 0),
        )
        # За пределами периода (раньше start_date)
        await insert_order(
            test_db,
            user_id=101,
            user_name="User2",
            items=[{"name": "Капучино", "price": 200, "quantity": 1}],
            total=200,
            status="completed",
            created_at=datetime(2026, 1, 25, 10, 0, 0),
        )

        with patch("bot.stats.DB_PATH", test_db), \
             patch("bot.stats.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 7)
            mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

            stats = await get_weekly_stats(days=7)

        assert stats.total_orders == 1
        assert stats.total_revenue == 220

    @pytest.mark.asyncio
    async def test_custom_days_параметр(self, test_db):
        """Проверяем работу с кастомным периодом (days=3)."""
        # 5-7 февраля при days=3 и today=7 февраля
        await insert_order(
            test_db,
            user_id=100,
            user_name="User1",
            items=[{"name": "Латте", "price": 220, "quantity": 1}],
            total=220,
            status="completed",
            created_at=datetime(2026, 2, 6, 9, 0, 0),
        )
        # За пределами 3-дневного периода
        await insert_order(
            test_db,
            user_id=101,
            user_name="User2",
            items=[{"name": "Капучино", "price": 200, "quantity": 1}],
            total=200,
            status="completed",
            created_at=datetime(2026, 2, 3, 10, 0, 0),
        )

        with patch("bot.stats.DB_PATH", test_db), \
             patch("bot.stats.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 7)
            mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

            stats = await get_weekly_stats(days=3)

        assert stats.start_date == date(2026, 2, 5)
        assert stats.end_date == date(2026, 2, 7)
        assert stats.total_orders == 1


class TestFormatStats:
    """Тесты для format_stats."""

    def test_пустой_день_возвращает_сообщение_об_отсутствии_заказов(self):
        """При total_orders=0 возвращает 'Заказов не было'."""
        stats = DailyStats(
            target_date=date(2026, 2, 1),
            total_orders=0,
            completed_orders=0,
            cancelled_orders=0,
            total_revenue=0,
            avg_order_value=0,
            popular_items=[],
            hourly_distribution={},
        )

        result = format_stats(stats)

        assert "01.02.2026" in result
        assert "Заказов не было" in result

    def test_день_с_данными_форматирует_все_секции(self):
        """Проверяем форматирование всех секций статистики."""
        stats = DailyStats(
            target_date=date(2026, 2, 1),
            total_orders=5,
            completed_orders=3,
            cancelled_orders=1,
            total_revenue=1500,
            avg_order_value=500,
            popular_items=[("Латте", 10), ("Капучино", 7), ("Эспрессо", 3)],
            hourly_distribution={9: 3, 10: 2, 12: 1},
        )

        result = format_stats(stats)

        # Заголовок с датой
        assert "01.02.2026" in result
        # Количество заказов
        assert "Заказов: 5" in result
        assert "Выполнено: 3" in result
        assert "Отменено: 1" in result
        # Выручка (с пробелами как разделителями тысяч)
        assert "1 500₽" in result
        assert "500₽" in result
        # Топ позиций
        assert "Топ позиций" in result
        assert "Латте — 10 шт" in result
        assert "Капучино — 7 шт" in result
        assert "Эспрессо — 3 шт" in result
        # Пиковые часы (топ-2)
        assert "Пиковые часы" in result
        assert "09:00-10:00 — 3 заказов" in result
        assert "10:00-11:00 — 2 заказов" in result

    def test_форматирование_больших_чисел(self):
        """Проверяем форматирование выручки с разделителем тысяч."""
        stats = DailyStats(
            target_date=date(2026, 2, 1),
            total_orders=100,
            completed_orders=90,
            cancelled_orders=10,
            total_revenue=125000,
            avg_order_value=1388,
            popular_items=[],
            hourly_distribution={},
        )

        result = format_stats(stats)

        assert "125 000₽" in result
        assert "1 388₽" in result

    def test_без_popular_items_секция_не_отображается(self):
        """Если нет popular_items, секция 'Топ позиций' отсутствует."""
        stats = DailyStats(
            target_date=date(2026, 2, 1),
            total_orders=1,
            completed_orders=1,
            cancelled_orders=0,
            total_revenue=220,
            avg_order_value=220,
            popular_items=[],
            hourly_distribution={9: 1},
        )

        result = format_stats(stats)

        assert "Топ позиций" not in result

    def test_без_hourly_distribution_секция_не_отображается(self):
        """Если нет hourly_distribution, секция 'Пиковые часы' отсутствует."""
        stats = DailyStats(
            target_date=date(2026, 2, 1),
            total_orders=1,
            completed_orders=1,
            cancelled_orders=0,
            total_revenue=220,
            avg_order_value=220,
            popular_items=[("Латте", 1)],
            hourly_distribution={},
        )

        result = format_stats(stats)

        assert "Пиковые часы" not in result


class TestFormatWeeklyStats:
    """Тесты для format_weekly_stats."""

    def test_пустой_период_возвращает_сообщение_об_отсутствии_заказов(self):
        """При total_orders=0 возвращает 'Заказов не было'."""
        stats = WeeklyStats(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 7),
            total_orders=0,
            total_revenue=0,
            avg_order_value=0,
            daily_orders={},
        )

        result = format_weekly_stats(stats)

        assert "7 дней" in result
        assert "Заказов не было" in result

    def test_период_с_данными_форматирует_все_секции(self):
        """Проверяем форматирование всех секций недельной статистики."""
        stats = WeeklyStats(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 7),
            total_orders=25,
            total_revenue=5500,
            avg_order_value=220,
            daily_orders={"Пн": 5, "Вт": 4, "Ср": 3, "Чт": 4, "Пт": 6, "Сб": 2, "Вс": 1},
        )

        result = format_weekly_stats(stats)

        # Заголовок
        assert "7 дней" in result
        # Количество заказов
        assert "Заказов: 25" in result
        # Выручка
        assert "5 500₽" in result
        assert "220₽" in result
        # По дням
        assert "По дням" in result
        assert "Пн: 5" in result
        assert "Сб: 2" in result

    def test_daily_orders_отсутствующие_дни_показывают_ноль(self):
        """Дни без заказов отображаются с нулём."""
        stats = WeeklyStats(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 7),
            total_orders=3,
            total_revenue=660,
            avg_order_value=220,
            daily_orders={"Пн": 2, "Ср": 1},
        )

        result = format_weekly_stats(stats)

        assert "Пн: 2" in result
        assert "Вт: 0" in result
        assert "Ср: 1" in result
        assert "Чт: 0" in result

    def test_без_daily_orders_секция_не_отображается(self):
        """Если daily_orders пустой, секция 'По дням' отсутствует."""
        stats = WeeklyStats(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 7),
            total_orders=3,
            total_revenue=660,
            avg_order_value=220,
            daily_orders={},
        )

        result = format_weekly_stats(stats)

        assert "По дням" not in result
