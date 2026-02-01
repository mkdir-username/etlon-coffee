"""Интеграционные тесты для handlers Etlon Coffee Bot."""
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
import pytest_asyncio
from aiogram.fsm.context import FSMContext

from bot.states import OrderState
from bot.models import CartItem, OrderStatus


class TestClientHandlersFSM:
    """Тесты FSM переходов в client handlers."""

    @pytest.mark.asyncio
    async def test_start_sets_browsing_state(
        self,
        populated_db: Path,
        make_message,
        fsm_context_factory,
        monkeypatch,
    ):
        """cmd_start устанавливает состояние browsing_menu."""
        monkeypatch.setattr("bot.database.DB_PATH", populated_db)

        from bot.handlers.client import cmd_start

        user_id = 100001
        msg = make_message(user_id, "/start")
        state = await fsm_context_factory(user_id)

        await cmd_start(msg, state)

        current_state = await state.get_state()
        assert current_state == OrderState.browsing_menu

    @pytest.mark.asyncio
    async def test_add_to_cart_transitions_to_selecting_size(
        self,
        populated_db_with_modifiers: Path,
        make_callback,
        fsm_context_factory,
        monkeypatch,
    ):
        """Добавление позиции в корзину переводит в selecting_size."""
        monkeypatch.setattr("bot.database.DB_PATH", populated_db_with_modifiers)

        from bot.handlers.client import add_to_cart

        user_id = 100002
        cb = make_callback(user_id, "menu:1")
        state = await fsm_context_factory(user_id)
        await state.set_state(OrderState.browsing_menu)

        await add_to_cart(cb, state)

        current_state = await state.get_state()
        assert current_state == OrderState.selecting_size

    @pytest.mark.asyncio
    async def test_size_selection_transitions_to_modifiers(
        self,
        populated_db_with_modifiers: Path,
        make_callback,
        fsm_context_factory,
        monkeypatch,
    ):
        """Выбор размера переводит в selecting_modifiers."""
        monkeypatch.setattr("bot.database.DB_PATH", populated_db_with_modifiers)

        from bot.handlers.client import select_size

        user_id = 100003
        cb = make_callback(user_id, "size:1:M")
        state = await fsm_context_factory(user_id)
        await state.set_state(OrderState.selecting_size)
        await state.update_data(
            pending_item_id=1,
            pending_item_name="Эспрессо",
            pending_item_price=120,
        )

        await select_size(cb, state)

        current_state = await state.get_state()
        assert current_state == OrderState.selecting_modifiers

    @pytest.mark.asyncio
    async def test_modifiers_done_adds_to_cart(
        self,
        populated_db_with_modifiers: Path,
        make_callback,
        fsm_context_factory,
        monkeypatch,
    ):
        """mod:done добавляет позицию в корзину и возвращает в browsing_menu."""
        monkeypatch.setattr("bot.database.DB_PATH", populated_db_with_modifiers)

        from bot.handlers.client import modifiers_done

        user_id = 100004
        cb = make_callback(user_id, "mod:done:1:M")
        state = await fsm_context_factory(user_id)
        await state.set_state(OrderState.selecting_modifiers)
        await state.update_data(
            pending_item_id=1,
            pending_item_name="Эспрессо",
            pending_item_price=120,
            pending_size="M",
            pending_size_name="Средний 350мл",
            pending_size_price=40,
            pending_modifiers=[],
            cart=[],
        )

        await modifiers_done(cb, state)

        current_state = await state.get_state()
        assert current_state == OrderState.browsing_menu

        data = await state.get_data()
        assert len(data.get("cart", [])) == 1
        assert data["cart"][0]["name"] == "Эспрессо"

    @pytest.mark.asyncio
    async def test_checkout_transitions_to_selecting_time(
        self,
        populated_db: Path,
        make_callback,
        fsm_context_factory,
        monkeypatch,
    ):
        """cart:checkout переводит в selecting_time."""
        monkeypatch.setattr("bot.database.DB_PATH", populated_db)

        from bot.handlers.client import checkout

        user_id = 100005
        cb = make_callback(user_id, "cart:checkout")
        state = await fsm_context_factory(user_id)
        await state.set_state(OrderState.browsing_menu)
        await state.update_data(
            cart=[{
                "menu_item_id": 1,
                "name": "Эспрессо",
                "price": 120,
                "quantity": 1,
            }]
        )

        await checkout(cb, state)

        current_state = await state.get_state()
        assert current_state == OrderState.selecting_time

    @pytest.mark.asyncio
    async def test_time_selection_transitions_to_applying_bonus(
        self,
        populated_db: Path,
        make_callback,
        fsm_context_factory,
        monkeypatch,
    ):
        """time:15 переводит в applying_bonus если есть баллы."""
        monkeypatch.setattr("bot.database.DB_PATH", populated_db)
        monkeypatch.setattr("bot.loyalty.DB_PATH", populated_db)

        from tests.conftest import insert_loyalty
        from bot.handlers.client import select_time

        user_id = 100006
        # Добавляем баллы для перехода в applying_bonus
        await insert_loyalty(populated_db, user_id, points=100, stamps=0)

        cb = make_callback(user_id, "time:15")
        state = await fsm_context_factory(user_id)
        await state.set_state(OrderState.selecting_time)
        await state.update_data(
            cart=[{
                "menu_item_id": 1,
                "name": "Эспрессо",
                "price": 120,
                "quantity": 1,
            }]
        )

        await select_time(cb, state)

        current_state = await state.get_state()
        assert current_state == OrderState.applying_bonus

        data = await state.get_data()
        assert data.get("pickup_time") == "через 15 мин"

    @pytest.mark.asyncio
    async def test_bonus_skip_transitions_to_confirming(
        self,
        populated_db: Path,
        make_callback,
        fsm_context_factory,
        monkeypatch,
    ):
        """bonus:skip переводит в confirming."""
        monkeypatch.setattr("bot.database.DB_PATH", populated_db)

        from bot.handlers.client import bonus_skip

        user_id = 100007
        cb = make_callback(user_id, "bonus:skip")
        state = await fsm_context_factory(user_id)
        await state.set_state(OrderState.applying_bonus)
        await state.update_data(
            cart=[{
                "menu_item_id": 1,
                "name": "Эспрессо",
                "price": 120,
                "quantity": 1,
            }],
            pickup_time="через 15 мин",
        )

        await bonus_skip(cb, state)

        current_state = await state.get_state()
        assert current_state == OrderState.confirming


class TestCartOperations:
    """Тесты операций с корзиной."""

    @pytest.mark.asyncio
    async def test_cart_increment(
        self,
        populated_db: Path,
        make_callback,
        fsm_context_factory,
        monkeypatch,
    ):
        """cart:inc увеличивает количество позиции."""
        monkeypatch.setattr("bot.database.DB_PATH", populated_db)

        from bot.handlers.client import cart_increase

        user_id = 100010
        cb = make_callback(user_id, "cart:inc:1")
        state = await fsm_context_factory(user_id)
        await state.set_state(OrderState.browsing_menu)
        await state.update_data(
            cart=[{
                "menu_item_id": 1,
                "name": "Эспрессо",
                "price": 120,
                "quantity": 1,
            }]
        )

        await cart_increase(cb, state)

        data = await state.get_data()
        assert data["cart"][0]["quantity"] == 2

    @pytest.mark.asyncio
    async def test_cart_decrement(
        self,
        populated_db: Path,
        make_callback,
        fsm_context_factory,
        monkeypatch,
    ):
        """cart:dec уменьшает количество позиции."""
        monkeypatch.setattr("bot.database.DB_PATH", populated_db)

        from bot.handlers.client import cart_decrease

        user_id = 100011
        cb = make_callback(user_id, "cart:dec:1")
        state = await fsm_context_factory(user_id)
        await state.set_state(OrderState.browsing_menu)
        await state.update_data(
            cart=[{
                "menu_item_id": 1,
                "name": "Эспрессо",
                "price": 120,
                "quantity": 2,
            }]
        )

        await cart_decrease(cb, state)

        data = await state.get_data()
        assert data["cart"][0]["quantity"] == 1

    @pytest.mark.asyncio
    async def test_cart_decrement_removes_item_at_zero(
        self,
        populated_db: Path,
        make_callback,
        fsm_context_factory,
        monkeypatch,
    ):
        """cart:dec при quantity=1 удаляет позицию."""
        monkeypatch.setattr("bot.database.DB_PATH", populated_db)

        from bot.handlers.client import cart_decrease

        user_id = 100012
        cb = make_callback(user_id, "cart:dec:1")
        state = await fsm_context_factory(user_id)
        await state.set_state(OrderState.browsing_menu)
        await state.update_data(
            cart=[{
                "menu_item_id": 1,
                "name": "Эспрессо",
                "price": 120,
                "quantity": 1,
            }]
        )

        await cart_decrease(cb, state)

        data = await state.get_data()
        assert len(data["cart"]) == 0


class TestHistoryHandlers:
    """Тесты handlers истории заказов."""

    @pytest.mark.asyncio
    async def test_history_command_shows_orders(
        self,
        populated_db: Path,
        make_message,
        fsm_context_factory,
        monkeypatch,
    ):
        """/history показывает заказы пользователя."""
        monkeypatch.setattr("bot.database.DB_PATH", populated_db)

        from tests.conftest import insert_order

        user_id = 100020
        await insert_order(
            populated_db,
            user_id=user_id,
            user_name="Test User",
            items=[{"menu_item_id": 1, "name": "Эспрессо", "price": 120, "quantity": 1}],
            total=120,
        )

        from bot.handlers.client import cmd_history

        msg = make_message(user_id, "/history")
        state = await fsm_context_factory(user_id)

        await cmd_history(msg, state)

        msg.answer.assert_called_once()
        call_args = msg.answer.call_args
        assert "История" in call_args[0][0] or "заказ" in call_args[0][0].lower()


class TestFavoritesHandlers:
    """Тесты handlers избранного."""

    @pytest.mark.asyncio
    async def test_add_favorite(
        self,
        populated_db: Path,
        make_callback,
        fsm_context_factory,
        monkeypatch,
    ):
        """fav:add добавляет позицию в избранное."""
        monkeypatch.setattr("bot.database.DB_PATH", populated_db)

        from bot.handlers.client import fav_add
        from tests.conftest import get_favorites

        user_id = 100030
        cb = make_callback(user_id, "fav:add:1")
        state = await fsm_context_factory(user_id)

        await fav_add(cb)

        favorites = await get_favorites(populated_db, user_id)
        assert 1 in favorites

    @pytest.mark.asyncio
    async def test_remove_favorite(
        self,
        populated_db: Path,
        make_callback,
        fsm_context_factory,
        monkeypatch,
    ):
        """fav:remove удаляет позицию из избранного."""
        monkeypatch.setattr("bot.database.DB_PATH", populated_db)

        from bot.handlers.client import fav_remove
        from tests.conftest import add_favorite, get_favorites

        user_id = 100031
        await add_favorite(populated_db, user_id, 1)

        cb = make_callback(user_id, "fav:remove:1")
        state = await fsm_context_factory(user_id)

        await fav_remove(cb)

        favorites = await get_favorites(populated_db, user_id)
        assert 1 not in favorites


class TestCancelOrder:
    """Тесты отмены заказа."""

    @pytest.mark.asyncio
    async def test_cancel_confirmed_order(
        self,
        populated_db: Path,
        make_callback,
        fsm_context_factory,
        mock_bot,
        monkeypatch,
    ):
        """cancel:{id} отменяет подтверждённый заказ."""
        monkeypatch.setattr("bot.database.DB_PATH", populated_db)
        monkeypatch.setattr("bot.loyalty.DB_PATH", populated_db)

        from tests.conftest import insert_order, get_order_by_id

        user_id = 100040
        order_id = await insert_order(
            populated_db,
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

        order = await get_order_by_id(populated_db, order_id)
        assert order["status"] == "cancelled"


class TestBonusApplication:
    """Тесты списания баллов."""

    @pytest.mark.asyncio
    async def test_bonus_use_applies_discount(
        self,
        populated_db: Path,
        make_callback,
        fsm_context_factory,
        monkeypatch,
    ):
        """bonus:use:{amount} применяет скидку."""
        monkeypatch.setattr("bot.database.DB_PATH", populated_db)
        monkeypatch.setattr("bot.loyalty.DB_PATH", populated_db)

        from tests.conftest import insert_loyalty

        user_id = 100050
        await insert_loyalty(populated_db, user_id, points=200, stamps=0)

        from bot.handlers.client import bonus_use

        cb = make_callback(user_id, "bonus:use:100")
        state = await fsm_context_factory(user_id)
        await state.set_state(OrderState.applying_bonus)
        await state.update_data(
            cart=[{
                "menu_item_id": 1,
                "name": "Эспрессо",
                "price": 500,
                "quantity": 1,
            }],
            pickup_time="через 15 мин",
        )

        await bonus_use(cb, state)

        data = await state.get_data()
        assert data.get("bonus_used") == 100

    @pytest.mark.asyncio
    async def test_bonus_max_uses_maximum_allowed(
        self,
        populated_db: Path,
        make_callback,
        fsm_context_factory,
        monkeypatch,
    ):
        """bonus:max использует максимально допустимое количество баллов."""
        monkeypatch.setattr("bot.database.DB_PATH", populated_db)
        monkeypatch.setattr("bot.loyalty.DB_PATH", populated_db)

        from tests.conftest import insert_loyalty

        user_id = 100051
        # 500 баллов, заказ на 300₽ → max 30% = 90₽
        await insert_loyalty(populated_db, user_id, points=500, stamps=0)

        from bot.handlers.client import bonus_max

        cb = make_callback(user_id, "bonus:max")
        state = await fsm_context_factory(user_id)
        await state.set_state(OrderState.applying_bonus)
        await state.update_data(
            cart=[{
                "menu_item_id": 1,
                "name": "Капучино",
                "price": 300,
                "quantity": 1,
            }],
            pickup_time="через 15 мин",
        )

        await bonus_max(cb, state)

        data = await state.get_data()
        # max 30% от 300 = 90
        assert data.get("bonus_used") == 90


class TestRepeatOrder:
    """Тесты повторного заказа."""

    @pytest.mark.asyncio
    async def test_repeat_order_adds_items_to_cart(
        self,
        populated_db: Path,
        make_callback,
        fsm_context_factory,
        monkeypatch,
    ):
        """repeat:{id} добавляет позиции заказа в корзину."""
        monkeypatch.setattr("bot.database.DB_PATH", populated_db)

        from tests.conftest import insert_order

        user_id = 100060
        order_id = await insert_order(
            populated_db,
            user_id=user_id,
            user_name="Test User",
            items=[
                {"menu_item_id": 1, "name": "Эспрессо", "price": 120, "quantity": 2},
                {"menu_item_id": 2, "name": "Американо", "price": 150, "quantity": 1},
            ],
            total=390,
        )

        from bot.handlers.client import repeat_order

        cb = make_callback(user_id, f"repeat:{order_id}")
        state = await fsm_context_factory(user_id)
        await state.update_data(cart=[])

        await repeat_order(cb, state)

        data = await state.get_data()
        cart = data.get("cart", [])
        # Проверяем, что позиции добавлены (если доступны)
        assert len(cart) >= 1


class TestProfileHandler:
    """Тесты /profile команды."""

    @pytest.mark.asyncio
    async def test_profile_shows_loyalty_info(
        self,
        populated_db: Path,
        make_message,
        fsm_context_factory,
        monkeypatch,
    ):
        """/profile показывает информацию о баллах и штампах."""
        monkeypatch.setattr("bot.database.DB_PATH", populated_db)
        monkeypatch.setattr("bot.loyalty.DB_PATH", populated_db)

        from tests.conftest import insert_loyalty

        user_id = 100070
        await insert_loyalty(populated_db, user_id, points=150, stamps=3, total_orders=5, total_spent=2500)

        from bot.handlers.client import cmd_profile

        msg = make_message(user_id, "/profile")
        state = await fsm_context_factory(user_id)

        await cmd_profile(msg)

        msg.answer.assert_called_once()
        call_args = msg.answer.call_args
        response_text = call_args[0][0]
        # Проверяем наличие ключевой информации
        assert "150" in response_text or "балл" in response_text.lower()
