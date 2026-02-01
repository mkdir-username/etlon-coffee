"""E2E тесты полных пользовательских флоу Etlon Coffee Bot."""
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
import pytest_asyncio
from aiogram.fsm.context import FSMContext

from bot.states import OrderState
from bot.models import OrderStatus


class TestFullOrderFlow:
    """E2E: Полный флоу заказа от /start до подтверждения."""

    @pytest.mark.asyncio
    async def test_complete_order_flow_without_modifiers(
        self,
        populated_db_with_modifiers: Path,
        make_message,
        make_callback,
        fsm_context_factory,
        mock_bot,
        monkeypatch,
    ):
        """
        Полный флоу заказа без модификаторов:
        /start → menu:1 → size:1:S → mod:done → cart:checkout → time:15 → bonus:skip → confirm:yes
        """
        monkeypatch.setattr("bot.database.DB_PATH", populated_db_with_modifiers)
        monkeypatch.setattr("bot.loyalty.DB_PATH", populated_db_with_modifiers)

        from bot.handlers.client import (
            cmd_start,
            add_to_cart,
            select_size,
            modifiers_done,
            checkout,
            select_time,
            bonus_skip,
            confirm_order,
        )
        from tests.conftest import get_user_orders, get_loyalty, insert_loyalty

        user_id = 200001
        # Добавляем баллы для перехода в applying_bonus
        await insert_loyalty(populated_db_with_modifiers, user_id, points=50, stamps=0)

        state = await fsm_context_factory(user_id)

        # 1. /start
        msg = make_message(user_id, "/start")
        await cmd_start(msg, state)
        assert await state.get_state() == OrderState.browsing_menu

        # 2. Выбор позиции меню
        cb = make_callback(user_id, "menu:1")
        await add_to_cart(cb, state)
        assert await state.get_state() == OrderState.selecting_size

        # 3. Выбор размера S
        cb = make_callback(user_id, "size:1:S")
        await select_size(cb, state)
        assert await state.get_state() == OrderState.selecting_modifiers

        # 4. Пропуск модификаторов
        cb = make_callback(user_id, "mod:done:1:S")
        await modifiers_done(cb, state)
        assert await state.get_state() == OrderState.browsing_menu

        # Проверяем корзину
        data = await state.get_data()
        assert len(data["cart"]) == 1
        assert data["cart"][0]["name"] == "Эспрессо"

        # 5. Checkout
        cb = make_callback(user_id, "cart:checkout")
        await checkout(cb, state)
        assert await state.get_state() == OrderState.selecting_time

        # 6. Выбор времени
        cb = make_callback(user_id, "time:15")
        await select_time(cb, state)
        assert await state.get_state() == OrderState.applying_bonus

        # 7. Пропуск бонусов
        cb = make_callback(user_id, "bonus:skip")
        await bonus_skip(cb, state)
        assert await state.get_state() == OrderState.confirming

        # 8. Подтверждение заказа
        cb = make_callback(user_id, "confirm:yes")
        await confirm_order(cb, state, mock_bot)

        # ПРОВЕРКИ
        orders = await get_user_orders(populated_db_with_modifiers, user_id, limit=1)
        assert len(orders) == 1
        assert orders[0]["status"] == "confirmed"
        assert orders[0]["total"] == 120  # Эспрессо S = 120₽

        loyalty = await get_loyalty(populated_db_with_modifiers, user_id)
        assert loyalty is not None
        # Было 50, начислено 5 (120//100 * 5 = 5) = 55
        assert loyalty["points"] == 55
        assert loyalty["stamps"] == 1


class TestOrderWithModifiers:
    """E2E: Заказ с модификаторами."""

    @pytest.mark.asyncio
    async def test_order_with_modifiers_calculates_price_correctly(
        self,
        populated_db_with_modifiers: Path,
        make_message,
        make_callback,
        fsm_context_factory,
        mock_bot,
        monkeypatch,
    ):
        """
        Заказ с модификаторами: цена = база + размер + модификаторы
        Латте (220) + M (+40) + Ванильный сироп (50) = 310₽
        """
        monkeypatch.setattr("bot.database.DB_PATH", populated_db_with_modifiers)
        monkeypatch.setattr("bot.loyalty.DB_PATH", populated_db_with_modifiers)

        from bot.handlers.client import (
            cmd_start,
            add_to_cart,
            select_size,
            toggle_modifier,
            modifiers_done,
            checkout,
            select_time,
            bonus_skip,
            confirm_order,
        )
        from tests.conftest import get_user_orders

        user_id = 200002
        state = await fsm_context_factory(user_id)

        # 1. /start
        msg = make_message(user_id, "/start")
        await cmd_start(msg, state)

        # 2. Выбор Латте (id=3)
        cb = make_callback(user_id, "menu:3")
        await add_to_cart(cb, state)

        # 3. Выбор размера M (+40₽)
        cb = make_callback(user_id, "size:3:M")
        await select_size(cb, state)

        # 4. Добавляем Ванильный сироп (id=1, +50₽)
        cb = make_callback(user_id, "mod:toggle:3:M:1")
        await toggle_modifier(cb, state)

        # 5. Завершаем выбор модификаторов
        cb = make_callback(user_id, "mod:done:3:M")
        await modifiers_done(cb, state)

        # Проверяем корзину
        data = await state.get_data()
        cart_item = data["cart"][0]
        # price включает всё: 220 (база) + 40 (размер M) + 50 (сироп) = 310
        assert cart_item["price"] == 310
        assert cart_item["modifiers_price"] == 50

        # 6-9. Завершаем заказ
        cb = make_callback(user_id, "cart:checkout")
        await checkout(cb, state)

        cb = make_callback(user_id, "time:15")
        await select_time(cb, state)

        cb = make_callback(user_id, "bonus:skip")
        await bonus_skip(cb, state)

        cb = make_callback(user_id, "confirm:yes")
        await confirm_order(cb, state, mock_bot)

        # ПРОВЕРКИ
        orders = await get_user_orders(populated_db_with_modifiers, user_id, limit=1)
        assert len(orders) == 1
        # Итого: 260 (с размером) + 50 (модификатор) = 310₽
        assert orders[0]["total"] == 310


class TestOrderWithBonusRedemption:
    """E2E: Заказ со списанием баллов."""

    @pytest.mark.asyncio
    async def test_order_with_bonus_points_redemption(
        self,
        populated_db_with_modifiers: Path,
        make_message,
        make_callback,
        fsm_context_factory,
        mock_bot,
        monkeypatch,
    ):
        """
        Накопить баллы → новый заказ → bonus:use:100
        Скидка применена, баллы списаны.
        """
        monkeypatch.setattr("bot.database.DB_PATH", populated_db_with_modifiers)
        monkeypatch.setattr("bot.loyalty.DB_PATH", populated_db_with_modifiers)

        from tests.conftest import insert_loyalty, get_loyalty, get_user_orders

        user_id = 200003
        # Начинаем с 200 баллов
        await insert_loyalty(populated_db_with_modifiers, user_id, points=200, stamps=2)

        from bot.handlers.client import (
            cmd_start,
            add_to_cart,
            select_size,
            modifiers_done,
            checkout,
            select_time,
            bonus_use,
            confirm_order,
        )

        state = await fsm_context_factory(user_id)

        # Делаем заказ на 560₽ (Капучино L × 2)
        msg = make_message(user_id, "/start")
        await cmd_start(msg, state)

        # Добавляем Капучино (id=4, 200₽)
        cb = make_callback(user_id, "menu:4")
        await add_to_cart(cb, state)
        cb = make_callback(user_id, "size:4:L")  # +80₽
        await select_size(cb, state)
        cb = make_callback(user_id, "mod:done:4:L")
        await modifiers_done(cb, state)

        # Добавляем ещё Капучино
        cb = make_callback(user_id, "menu:4")
        await add_to_cart(cb, state)
        cb = make_callback(user_id, "size:4:L")
        await select_size(cb, state)
        cb = make_callback(user_id, "mod:done:4:L")
        await modifiers_done(cb, state)

        # Checkout
        cb = make_callback(user_id, "cart:checkout")
        await checkout(cb, state)

        cb = make_callback(user_id, "time:20")
        await select_time(cb, state)

        # Списываем 100 баллов
        cb = make_callback(user_id, "bonus:use:100")
        await bonus_use(cb, state)

        # Подтверждаем
        cb = make_callback(user_id, "confirm:yes")
        await confirm_order(cb, state, mock_bot)

        # ПРОВЕРКИ
        orders = await get_user_orders(populated_db_with_modifiers, user_id, limit=1)
        assert len(orders) == 1

        # order.total хранит полную сумму (до скидки), скидка применяется при отображении
        order = orders[0]
        assert order["total"] == 560  # 2 × Капучино L = 2 × 280 = 560

        loyalty = await get_loyalty(populated_db_with_modifiers, user_id)
        # Было 200, списали 100, начислили 25 (560//100 * 5 = 25) = 125
        assert loyalty["points"] == 125


class TestOrderCancellation:
    """E2E: Отмена заказа."""

    @pytest.mark.asyncio
    async def test_cancel_order_changes_status(
        self,
        populated_db_with_modifiers: Path,
        make_callback,
        fsm_context_factory,
        mock_bot,
        monkeypatch,
    ):
        """
        Создать заказ → cancel:{id}
        Статус CANCELLED.
        """
        monkeypatch.setattr("bot.database.DB_PATH", populated_db_with_modifiers)
        monkeypatch.setattr("bot.loyalty.DB_PATH", populated_db_with_modifiers)

        from tests.conftest import (
            insert_order,
            insert_loyalty,
            get_order_by_id,
        )

        user_id = 200004
        await insert_loyalty(populated_db_with_modifiers, user_id, points=100, stamps=3)

        # Создаём подтверждённый заказ
        order_id = await insert_order(
            populated_db_with_modifiers,
            user_id=user_id,
            user_name="Test User",
            items=[{"menu_item_id": 1, "name": "Эспрессо", "price": 120, "quantity": 1}],
            total=120,
            status="confirmed",
        )

        from bot.handlers.client import cancel_order

        cb = make_callback(user_id, f"cancel:{order_id}")
        state = await fsm_context_factory(user_id)

        await cancel_order(cb, mock_bot)

        # ПРОВЕРКИ
        order = await get_order_by_id(populated_db_with_modifiers, order_id)
        assert order["status"] == "cancelled"


class TestRepeatOrderFlow:
    """E2E: Повторный заказ из истории."""

    @pytest.mark.asyncio
    async def test_repeat_order_adds_available_items_to_cart(
        self,
        populated_db_with_modifiers: Path,
        make_message,
        make_callback,
        fsm_context_factory,
        monkeypatch,
    ):
        """
        Создать заказ → /history → repeat:{id}
        Доступные позиции добавлены в корзину.
        """
        monkeypatch.setattr("bot.database.DB_PATH", populated_db_with_modifiers)

        from tests.conftest import insert_order

        user_id = 200005
        order_id = await insert_order(
            populated_db_with_modifiers,
            user_id=user_id,
            user_name="Test User",
            items=[
                {"menu_item_id": 1, "name": "Эспрессо", "price": 120, "quantity": 2},
                {"menu_item_id": 3, "name": "Латте", "price": 220, "quantity": 1},
            ],
            total=460,
        )

        from bot.handlers.client import cmd_start, repeat_order

        state = await fsm_context_factory(user_id)

        # Start
        msg = make_message(user_id, "/start")
        await cmd_start(msg, state)

        # Repeat
        cb = make_callback(user_id, f"repeat:{order_id}")
        await repeat_order(cb, state)

        # ПРОВЕРКИ
        data = await state.get_data()
        cart = data.get("cart", [])
        # Должны быть обе позиции (они доступны)
        assert len(cart) >= 2
        item_names = [item["name"] for item in cart]
        assert "Эспрессо" in item_names
        assert "Латте" in item_names


class TestFavoritesFlow:
    """E2E: Работа с избранным."""

    @pytest.mark.asyncio
    async def test_add_and_remove_favorite(
        self,
        populated_db_with_modifiers: Path,
        make_message,
        make_callback,
        fsm_context_factory,
        monkeypatch,
    ):
        """
        /start → fav:add:1 → /favorites → fav:remove:1
        Добавление/удаление работает.
        """
        monkeypatch.setattr("bot.database.DB_PATH", populated_db_with_modifiers)

        from bot.handlers.client import (
            cmd_start,
            cmd_favorites,
            fav_add,
            fav_remove,
        )
        from tests.conftest import get_favorites

        user_id = 200006
        state = await fsm_context_factory(user_id)

        # Start
        msg = make_message(user_id, "/start")
        await cmd_start(msg, state)

        # Добавляем в избранное
        cb = make_callback(user_id, "fav:add:1")
        await fav_add(cb)

        favorites = await get_favorites(populated_db_with_modifiers, user_id)
        assert 1 in favorites

        # Просмотр избранного
        msg = make_message(user_id, "/favorites")
        await cmd_favorites(msg)

        # Удаляем из избранного
        cb = make_callback(user_id, "fav:remove:1")
        await fav_remove(cb)

        favorites = await get_favorites(populated_db_with_modifiers, user_id)
        assert 1 not in favorites


class TestProfileFlow:
    """E2E: Профиль пользователя."""

    @pytest.mark.asyncio
    async def test_profile_shows_correct_stats(
        self,
        populated_db_with_modifiers: Path,
        make_message,
        fsm_context_factory,
        monkeypatch,
    ):
        """
        Создать заказы → /profile
        Баллы, штампы, статистика верны.
        """
        monkeypatch.setattr("bot.database.DB_PATH", populated_db_with_modifiers)
        monkeypatch.setattr("bot.loyalty.DB_PATH", populated_db_with_modifiers)

        from tests.conftest import insert_loyalty, insert_order

        user_id = 200007
        await insert_loyalty(
            populated_db_with_modifiers,
            user_id,
            points=175,
            stamps=4,
            total_orders=10,
            total_spent=3500,
        )

        from bot.handlers.client import cmd_profile

        state = await fsm_context_factory(user_id)

        msg = make_message(user_id, "/profile")
        await cmd_profile(msg)

        # ПРОВЕРКИ
        msg.answer.assert_called_once()
        response_text = msg.answer.call_args[0][0]
        # Проверяем наличие ключевых данных
        assert "175" in response_text  # баллы
        assert "4" in response_text or "●●●●" in response_text  # штампы


class TestBaristaFlow:
    """E2E: Панель баристы."""

    @pytest.mark.asyncio
    async def test_barista_status_change_flow(
        self,
        populated_db_with_modifiers: Path,
        make_message,
        make_callback,
        fsm_context_factory,
        mock_bot,
        monkeypatch,
    ):
        """
        /barista → barista:status:{id}:preparing → barista:status:{id}:ready
        Статусы меняются, клиент уведомлён.
        """
        monkeypatch.setattr("bot.database.DB_PATH", populated_db_with_modifiers)

        barista_id = 300001
        # Мокаем helper-функцию _is_barista (обходим Pydantic Settings)
        monkeypatch.setattr(
            "bot.handlers.barista._is_barista",
            lambda uid: uid == barista_id
        )

        from tests.conftest import insert_order, get_order_by_id

        # Создаём заказ от клиента
        client_id = 200008
        order_id = await insert_order(
            populated_db_with_modifiers,
            user_id=client_id,
            user_name="Client User",
            items=[{"menu_item_id": 1, "name": "Эспрессо", "price": 120, "quantity": 1}],
            total=120,
            status="confirmed",
        )

        from bot.handlers.barista import (
            cmd_barista,
            change_status,
        )

        state = await fsm_context_factory(barista_id)

        # Бариста открывает панель
        msg = make_message(barista_id, "/barista")
        await cmd_barista(msg)

        # Меняем статус на PREPARING
        cb = make_callback(barista_id, f"barista:status:{order_id}:preparing")
        await change_status(cb, mock_bot)

        order = await get_order_by_id(populated_db_with_modifiers, order_id)
        assert order["status"] == "preparing"

        # Меняем статус на READY
        cb = make_callback(barista_id, f"barista:status:{order_id}:ready")
        await change_status(cb, mock_bot)

        order = await get_order_by_id(populated_db_with_modifiers, order_id)
        assert order["status"] == "ready"

        # Проверяем, что клиенту отправлено уведомление
        assert mock_bot.send_message.called
