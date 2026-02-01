"""Integration тесты для модуля bot/database.py."""
import json
import pytest
import aiosqlite
from datetime import datetime

from bot import database as db
from bot.models import OrderItem, OrderStatus
from tests.conftest import insert_order


# ==================== FAVORITES ====================


@pytest.mark.asyncio
class TestAddFavorite:
    """Тесты add_favorite."""

    async def test_add_favorite_new(self, populated_db):
        """Добавление новой позиции в избранное возвращает True."""
        result = await db.add_favorite(user_id=123, menu_item_id=1)

        assert result is True

    async def test_add_favorite_new_persists_in_db(self, populated_db):
        """Добавленная позиция сохраняется в БД."""
        user_id = 124
        menu_item_id = 2

        await db.add_favorite(user_id, menu_item_id)

        async with aiosqlite.connect(populated_db) as conn:
            cursor = await conn.execute(
                "SELECT user_id, menu_item_id FROM favorites WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()

        assert row is not None
        assert row[0] == user_id
        assert row[1] == menu_item_id

    async def test_add_favorite_duplicate_returns_false(self, populated_db):
        """Повторное добавление той же позиции возвращает False."""
        user_id = 125
        menu_item_id = 1

        await db.add_favorite(user_id, menu_item_id)
        result = await db.add_favorite(user_id, menu_item_id)

        assert result is False

    async def test_add_favorite_duplicate_no_extra_records(self, populated_db):
        """При повторном добавлении не создаётся дублирующая запись."""
        user_id = 126
        menu_item_id = 1

        await db.add_favorite(user_id, menu_item_id)
        await db.add_favorite(user_id, menu_item_id)

        async with aiosqlite.connect(populated_db) as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM favorites WHERE user_id = ? AND menu_item_id = ?",
                (user_id, menu_item_id)
            )
            row = await cursor.fetchone()

        assert row[0] == 1

    async def test_add_favorite_different_items(self, populated_db):
        """Можно добавить разные позиции в избранное одного пользователя."""
        user_id = 127

        result1 = await db.add_favorite(user_id, menu_item_id=1)
        result2 = await db.add_favorite(user_id, menu_item_id=2)

        assert result1 is True
        assert result2 is True


@pytest.mark.asyncio
class TestRemoveFavorite:
    """Тесты remove_favorite."""

    async def test_remove_favorite_existing(self, populated_db):
        """Удаление существующей позиции из избранного возвращает True."""
        user_id = 200
        menu_item_id = 1

        await db.add_favorite(user_id, menu_item_id)
        result = await db.remove_favorite(user_id, menu_item_id)

        assert result is True

    async def test_remove_favorite_existing_deletes_from_db(self, populated_db):
        """Удалённая позиция отсутствует в БД."""
        user_id = 201
        menu_item_id = 2

        await db.add_favorite(user_id, menu_item_id)
        await db.remove_favorite(user_id, menu_item_id)

        async with aiosqlite.connect(populated_db) as conn:
            cursor = await conn.execute(
                "SELECT 1 FROM favorites WHERE user_id = ? AND menu_item_id = ?",
                (user_id, menu_item_id)
            )
            row = await cursor.fetchone()

        assert row is None

    async def test_remove_favorite_nonexistent(self, populated_db):
        """Удаление несуществующей позиции возвращает False."""
        result = await db.remove_favorite(user_id=202, menu_item_id=999)

        assert result is False

    async def test_remove_favorite_wrong_user(self, populated_db):
        """Удаление позиции другого пользователя возвращает False."""
        await db.add_favorite(user_id=203, menu_item_id=1)

        result = await db.remove_favorite(user_id=999, menu_item_id=1)

        assert result is False


@pytest.mark.asyncio
class TestGetFavorites:
    """Тесты get_favorites."""

    async def test_get_favorites_empty(self, populated_db):
        """Пустое избранное возвращает пустой список."""
        result = await db.get_favorites(user_id=300)

        assert result == []

    async def test_get_favorites_with_items(self, populated_db):
        """Избранное с позициями возвращает список MenuItem."""
        user_id = 301
        await db.add_favorite(user_id, menu_item_id=1)
        await db.add_favorite(user_id, menu_item_id=2)

        result = await db.get_favorites(user_id)

        assert len(result) == 2
        assert all(hasattr(item, 'id') and hasattr(item, 'name') for item in result)

    async def test_get_favorites_excludes_unavailable(self, populated_db):
        """Скрытые позиции (available=0) не возвращаются."""
        user_id = 302
        # id=5 - Раф с available=0 в sample_menu_items
        await db.add_favorite(user_id, menu_item_id=5)
        await db.add_favorite(user_id, menu_item_id=1)

        result = await db.get_favorites(user_id)

        assert len(result) == 1
        assert result[0].id == 1

    async def test_get_favorites_correct_item_data(self, populated_db):
        """Возвращённые MenuItem содержат корректные данные."""
        user_id = 303
        await db.add_favorite(user_id, menu_item_id=1)

        result = await db.get_favorites(user_id)

        assert len(result) == 1
        assert result[0].id == 1
        assert result[0].name == "Эспрессо"
        assert result[0].price == 120


@pytest.mark.asyncio
class TestIsFavorite:
    """Тесты is_favorite."""

    async def test_is_favorite_true(self, populated_db):
        """Позиция в избранном возвращает True."""
        user_id = 400
        menu_item_id = 1

        await db.add_favorite(user_id, menu_item_id)
        result = await db.is_favorite(user_id, menu_item_id)

        assert result is True

    async def test_is_favorite_false(self, populated_db):
        """Позиция не в избранном возвращает False."""
        result = await db.is_favorite(user_id=401, menu_item_id=1)

        assert result is False

    async def test_is_favorite_wrong_item(self, populated_db):
        """Другая позиция того же пользователя возвращает False."""
        user_id = 402
        await db.add_favorite(user_id, menu_item_id=1)

        result = await db.is_favorite(user_id, menu_item_id=2)

        assert result is False


@pytest.mark.asyncio
class TestGetUserFavoriteIds:
    """Тесты get_user_favorite_ids."""

    async def test_get_user_favorite_ids_empty(self, populated_db):
        """Пустое избранное возвращает пустой set."""
        result = await db.get_user_favorite_ids(user_id=450)

        assert result == set()

    async def test_get_user_favorite_ids_with_items(self, populated_db):
        """Возвращает set ID избранных позиций."""
        user_id = 451
        await db.add_favorite(user_id, menu_item_id=1)
        await db.add_favorite(user_id, menu_item_id=3)

        result = await db.get_user_favorite_ids(user_id)

        assert result == {1, 3}


# ==================== ORDERS ====================


@pytest.mark.asyncio
class TestCreateOrder:
    """Тесты create_order."""

    async def test_create_order_returns_order(self, populated_db, sample_order_items):
        """Создание заказа возвращает Order."""
        order = await db.create_order(
            user_id=500,
            user_name="Test User",
            items=sample_order_items,
            pickup_time="через 15 мин"
        )

        assert order.id is not None
        assert order.user_id == 500
        assert order.user_name == "Test User"

    async def test_create_order_correct_total(self, populated_db, sample_order_items):
        """Total рассчитывается как сумма price * quantity."""
        order = await db.create_order(
            user_id=501,
            user_name="Test",
            items=sample_order_items,
            pickup_time="через 15 мин"
        )
        # 120*2 + 260*1 = 500
        expected_total = sum(item.price * item.quantity for item in sample_order_items)

        assert order.total == expected_total

    async def test_create_order_default_status_confirmed(self, populated_db, sample_order_items):
        """Статус по умолчанию CONFIRMED."""
        order = await db.create_order(
            user_id=502,
            user_name="Test",
            items=sample_order_items,
            pickup_time="через 15 мин"
        )

        assert order.status == OrderStatus.CONFIRMED

    async def test_create_order_persists_in_db(self, populated_db, sample_order_items):
        """Заказ сохраняется в БД."""
        order = await db.create_order(
            user_id=503,
            user_name="Persistent User",
            items=sample_order_items,
            pickup_time="через 20 мин"
        )

        async with aiosqlite.connect(populated_db) as conn:
            cursor = await conn.execute(
                "SELECT user_id, user_name, status FROM orders WHERE id = ?",
                (order.id,)
            )
            row = await cursor.fetchone()

        assert row is not None
        assert row[0] == 503
        assert row[1] == "Persistent User"
        assert row[2] == OrderStatus.CONFIRMED.value

    async def test_create_order_items_serialized(self, populated_db, sample_order_items):
        """Items сериализуются в JSON."""
        order = await db.create_order(
            user_id=504,
            user_name="Test",
            items=sample_order_items,
            pickup_time="через 15 мин"
        )

        async with aiosqlite.connect(populated_db) as conn:
            cursor = await conn.execute(
                "SELECT items FROM orders WHERE id = ?",
                (order.id,)
            )
            row = await cursor.fetchone()

        items_data = json.loads(row[0])
        assert len(items_data) == len(sample_order_items)
        assert items_data[0]["name"] == sample_order_items[0].name


@pytest.mark.asyncio
class TestGetOrder:
    """Тесты get_order."""

    async def test_get_order_existing(self, populated_db, sample_order_items):
        """Получение существующего заказа возвращает Order."""
        created = await db.create_order(
            user_id=600,
            user_name="Test",
            items=sample_order_items,
            pickup_time="через 15 мин"
        )

        order = await db.get_order(created.id)

        assert order is not None
        assert order.id == created.id
        assert order.user_id == 600

    async def test_get_order_nonexistent(self, populated_db):
        """Несуществующий заказ возвращает None."""
        order = await db.get_order(order_id=99999)

        assert order is None

    async def test_get_order_items_deserialized(self, populated_db, sample_order_items):
        """Items десериализуются в list[OrderItem]."""
        created = await db.create_order(
            user_id=601,
            user_name="Test",
            items=sample_order_items,
            pickup_time="через 15 мин"
        )

        order = await db.get_order(created.id)

        assert len(order.items) == len(sample_order_items)
        assert isinstance(order.items[0], OrderItem)
        assert order.items[0].name == sample_order_items[0].name


@pytest.mark.asyncio
class TestUpdateOrderStatus:
    """Тесты update_order_status."""

    async def test_update_status_confirmed_to_preparing(self, populated_db, sample_order_items):
        """CONFIRMED -> PREPARING."""
        order = await db.create_order(
            user_id=700,
            user_name="Test",
            items=sample_order_items,
            pickup_time="через 15 мин"
        )

        updated = await db.update_order_status(order.id, OrderStatus.PREPARING)

        assert updated is not None
        assert updated.status == OrderStatus.PREPARING

    async def test_update_status_preparing_to_ready(self, populated_db, sample_order_items):
        """PREPARING -> READY."""
        order = await db.create_order(
            user_id=701,
            user_name="Test",
            items=sample_order_items,
            pickup_time="через 15 мин"
        )
        await db.update_order_status(order.id, OrderStatus.PREPARING)

        updated = await db.update_order_status(order.id, OrderStatus.READY)

        assert updated.status == OrderStatus.READY

    async def test_update_status_ready_to_completed(self, populated_db, sample_order_items):
        """READY -> COMPLETED."""
        order = await db.create_order(
            user_id=702,
            user_name="Test",
            items=sample_order_items,
            pickup_time="через 15 мин"
        )
        await db.update_order_status(order.id, OrderStatus.PREPARING)
        await db.update_order_status(order.id, OrderStatus.READY)

        updated = await db.update_order_status(order.id, OrderStatus.COMPLETED)

        assert updated.status == OrderStatus.COMPLETED

    async def test_update_status_persists_in_db(self, populated_db, sample_order_items):
        """Обновлённый статус сохраняется в БД."""
        order = await db.create_order(
            user_id=703,
            user_name="Test",
            items=sample_order_items,
            pickup_time="через 15 мин"
        )

        await db.update_order_status(order.id, OrderStatus.PREPARING)

        async with aiosqlite.connect(populated_db) as conn:
            cursor = await conn.execute(
                "SELECT status FROM orders WHERE id = ?",
                (order.id,)
            )
            row = await cursor.fetchone()

        assert row[0] == OrderStatus.PREPARING.value


@pytest.mark.asyncio
class TestGetUserOrders:
    """Тесты get_user_orders."""

    async def test_get_user_orders_empty(self, populated_db):
        """У пользователя без заказов возвращается пустой список и total=0."""
        orders, total = await db.get_user_orders(user_id=800)

        assert orders == []
        assert total == 0

    async def test_get_user_orders_returns_orders(self, populated_db):
        """Возвращает заказы пользователя."""
        user_id = 801
        items = [{"menu_item_id": 1, "name": "Эспрессо", "price": 120, "quantity": 1}]

        await insert_order(populated_db, user_id, "Test", items, total=120)
        await insert_order(populated_db, user_id, "Test", items, total=120)

        orders, total = await db.get_user_orders(user_id)

        assert len(orders) == 2
        assert total == 2

    async def test_get_user_orders_pagination_limit(self, populated_db):
        """Параметр limit ограничивает количество заказов."""
        user_id = 802
        items = [{"menu_item_id": 1, "name": "Эспрессо", "price": 120, "quantity": 1}]

        for _ in range(7):
            await insert_order(populated_db, user_id, "Test", items, total=120)

        orders, total = await db.get_user_orders(user_id, limit=5, offset=0)

        assert len(orders) == 5
        assert total == 7

    async def test_get_user_orders_pagination_offset(self, populated_db):
        """Параметр offset пропускает первые N заказов."""
        user_id = 803
        items = [{"menu_item_id": 1, "name": "Эспрессо", "price": 120, "quantity": 1}]

        for _ in range(7):
            await insert_order(populated_db, user_id, "Test", items, total=120)

        orders, total = await db.get_user_orders(user_id, limit=5, offset=5)

        assert len(orders) == 2
        assert total == 7

    async def test_get_user_orders_sorted_by_created_at_desc(self, populated_db):
        """Заказы отсортированы по дате создания DESC (новые первыми)."""
        user_id = 804
        items = [{"menu_item_id": 1, "name": "Эспрессо", "price": 120, "quantity": 1}]

        await insert_order(
            populated_db, user_id, "Test", items, total=100,
            created_at=datetime(2026, 1, 1, 10, 0, 0)
        )
        await insert_order(
            populated_db, user_id, "Test", items, total=200,
            created_at=datetime(2026, 1, 2, 10, 0, 0)
        )

        orders, _ = await db.get_user_orders(user_id)

        assert orders[0].total == 200  # новый заказ первым
        assert orders[1].total == 100


@pytest.mark.asyncio
class TestCancelOrderByClient:
    """Тесты cancel_order_by_client."""

    async def test_cancel_confirmed_order_by_owner(self, populated_db):
        """Владелец может отменить заказ в статусе CONFIRMED."""
        user_id = 900
        items = [{"menu_item_id": 1, "name": "Эспрессо", "price": 120, "quantity": 1}]
        order_id = await insert_order(
            populated_db, user_id, "Test", items, total=120, status="confirmed"
        )

        success, message = await db.cancel_order_by_client(order_id, user_id)

        assert success is True
        assert "отменён" in message

    async def test_cancel_confirmed_order_status_changed(self, populated_db):
        """После отмены статус меняется на CANCELLED."""
        user_id = 901
        items = [{"menu_item_id": 1, "name": "Эспрессо", "price": 120, "quantity": 1}]
        order_id = await insert_order(
            populated_db, user_id, "Test", items, total=120, status="confirmed"
        )

        await db.cancel_order_by_client(order_id, user_id)

        order = await db.get_order(order_id)
        assert order.status == OrderStatus.CANCELLED

    async def test_cancel_preparing_order_fails(self, populated_db):
        """Нельзя отменить заказ в статусе PREPARING."""
        user_id = 902
        items = [{"menu_item_id": 1, "name": "Эспрессо", "price": 120, "quantity": 1}]
        order_id = await insert_order(
            populated_db, user_id, "Test", items, total=120, status="preparing"
        )

        success, message = await db.cancel_order_by_client(order_id, user_id)

        assert success is False
        assert "уже в работе" in message

    async def test_cancel_order_wrong_user_fails(self, populated_db):
        """Нельзя отменить чужой заказ."""
        owner_id = 903
        other_id = 999
        items = [{"menu_item_id": 1, "name": "Эспрессо", "price": 120, "quantity": 1}]
        order_id = await insert_order(
            populated_db, owner_id, "Test", items, total=120, status="confirmed"
        )

        success, message = await db.cancel_order_by_client(order_id, other_id)

        assert success is False
        assert "не найден" in message

    async def test_cancel_nonexistent_order_fails(self, populated_db):
        """Нельзя отменить несуществующий заказ."""
        success, message = await db.cancel_order_by_client(order_id=99999, user_id=904)

        assert success is False
        assert "не найден" in message

    async def test_cancel_ready_order_fails(self, populated_db):
        """Нельзя отменить заказ в статусе READY."""
        user_id = 905
        items = [{"menu_item_id": 1, "name": "Эспрессо", "price": 120, "quantity": 1}]
        order_id = await insert_order(
            populated_db, user_id, "Test", items, total=120, status="ready"
        )

        success, message = await db.cancel_order_by_client(order_id, user_id)

        assert success is False
        assert "уже в работе" in message


@pytest.mark.asyncio
class TestGetActiveOrders:
    """Тесты get_active_orders."""

    async def test_get_active_orders_excludes_completed(self, populated_db):
        """COMPLETED заказы не включаются."""
        items = [{"menu_item_id": 1, "name": "Эспрессо", "price": 120, "quantity": 1}]
        await insert_order(populated_db, 1000, "Test", items, total=120, status="completed")

        orders = await db.get_active_orders()

        assert all(o.status != OrderStatus.COMPLETED for o in orders)

    async def test_get_active_orders_excludes_cancelled(self, populated_db):
        """CANCELLED заказы не включаются."""
        items = [{"menu_item_id": 1, "name": "Эспрессо", "price": 120, "quantity": 1}]
        await insert_order(populated_db, 1001, "Test", items, total=120, status="cancelled")

        orders = await db.get_active_orders()

        assert all(o.status != OrderStatus.CANCELLED for o in orders)

    async def test_get_active_orders_includes_confirmed(self, populated_db):
        """CONFIRMED заказы включаются."""
        items = [{"menu_item_id": 1, "name": "Эспрессо", "price": 120, "quantity": 1}]
        await insert_order(populated_db, 1002, "Active User", items, total=120, status="confirmed")

        orders = await db.get_active_orders()

        assert any(o.user_name == "Active User" for o in orders)

    async def test_get_active_orders_includes_preparing(self, populated_db):
        """PREPARING заказы включаются."""
        items = [{"menu_item_id": 1, "name": "Эспрессо", "price": 120, "quantity": 1}]
        await insert_order(populated_db, 1003, "Preparing User", items, total=120, status="preparing")

        orders = await db.get_active_orders()

        assert any(o.user_name == "Preparing User" for o in orders)


# ==================== MENU ====================


@pytest.mark.asyncio
class TestGetMenu:
    """Тесты get_menu."""

    async def test_get_menu_returns_only_available(self, populated_db):
        """Возвращает только позиции с available=1."""
        menu = await db.get_menu()

        # id=5 (Раф) имеет available=0 в sample_menu_items
        assert all(item.available for item in menu)
        assert all(item.id != 5 for item in menu)

    async def test_get_menu_returns_menu_items(self, populated_db):
        """Возвращает список MenuItem."""
        menu = await db.get_menu()

        assert len(menu) == 4  # 5 позиций, 1 недоступна
        assert all(hasattr(item, 'id') and hasattr(item, 'name') for item in menu)


@pytest.mark.asyncio
class TestGetAllMenuItems:
    """Тесты get_all_menu_items."""

    async def test_get_all_menu_items_includes_unavailable(self, populated_db):
        """Включает позиции с available=0."""
        menu = await db.get_all_menu_items()

        assert len(menu) == 5
        unavailable = [item for item in menu if not item.available]
        assert len(unavailable) == 1
        assert unavailable[0].id == 5


@pytest.mark.asyncio
class TestToggleMenuItemAvailability:
    """Тесты toggle_menu_item_availability."""

    async def test_toggle_available_to_unavailable(self, populated_db):
        """available=1 -> available=0."""
        item = await db.get_menu_item(1)
        assert item.available is True

        updated = await db.toggle_menu_item_availability(1)

        assert updated.available is False

    async def test_toggle_unavailable_to_available(self, populated_db):
        """available=0 -> available=1."""
        item = await db.get_menu_item(5)
        assert item.available is False

        updated = await db.toggle_menu_item_availability(5)

        assert updated.available is True

    async def test_toggle_persists_in_db(self, populated_db):
        """Изменение сохраняется в БД."""
        await db.toggle_menu_item_availability(1)

        async with aiosqlite.connect(populated_db) as conn:
            cursor = await conn.execute(
                "SELECT available FROM menu_items WHERE id = ?",
                (1,)
            )
            row = await cursor.fetchone()

        assert row[0] == 0


@pytest.mark.asyncio
class TestGetMenuItem:
    """Тесты get_menu_item."""

    async def test_get_menu_item_existing(self, populated_db):
        """Существующая позиция возвращает MenuItem."""
        item = await db.get_menu_item(1)

        assert item is not None
        assert item.id == 1
        assert item.name == "Эспрессо"

    async def test_get_menu_item_nonexistent(self, populated_db):
        """Несуществующая позиция возвращает None."""
        item = await db.get_menu_item(99999)

        assert item is None


# ==================== MODIFIERS ====================


@pytest.mark.asyncio
class TestGetModifiers:
    """Тесты get_modifiers."""

    async def test_get_modifiers_empty_db(self, test_db):
        """Пустая таблица возвращает пустой список."""
        modifiers = await db.get_modifiers()

        assert modifiers == []

    async def test_get_modifiers_with_data(self, test_db, sample_modifiers):
        """Возвращает список модификаторов."""
        async with aiosqlite.connect(test_db) as conn:
            for mod in sample_modifiers:
                await conn.execute(
                    "INSERT INTO modifiers (id, name, category, price, is_available) VALUES (?, ?, ?, ?, 1)",
                    (mod["id"], mod["name"], mod["category"], mod["price"])
                )
            await conn.commit()

        modifiers = await db.get_modifiers()

        assert len(modifiers) == 5

    async def test_get_modifiers_by_category(self, test_db, sample_modifiers):
        """Фильтрация по категории."""
        async with aiosqlite.connect(test_db) as conn:
            for mod in sample_modifiers:
                await conn.execute(
                    "INSERT INTO modifiers (id, name, category, price, is_available) VALUES (?, ?, ?, ?, 1)",
                    (mod["id"], mod["name"], mod["category"], mod["price"])
                )
            await conn.commit()

        modifiers = await db.get_modifiers(category="syrup")

        assert len(modifiers) == 2
        assert all(m["category"] == "syrup" for m in modifiers)


@pytest.mark.asyncio
class TestGetMenuItemModifiers:
    """Тесты get_menu_item_modifiers."""

    async def test_get_menu_item_modifiers_no_links(self, populated_db):
        """Позиция без связанных модификаторов возвращает пустой список."""
        modifiers = await db.get_menu_item_modifiers(menu_item_id=1)

        assert modifiers == []

    async def test_get_menu_item_modifiers_with_links(self, populated_db, sample_modifiers):
        """Возвращает связанные модификаторы."""
        async with aiosqlite.connect(populated_db) as conn:
            for mod in sample_modifiers:
                await conn.execute(
                    "INSERT INTO modifiers (id, name, category, price, is_available) VALUES (?, ?, ?, ?, 1)",
                    (mod["id"], mod["name"], mod["category"], mod["price"])
                )
            # Связываем модификаторы 1, 2 с позицией меню 1
            await conn.execute(
                "INSERT INTO menu_item_modifiers (menu_item_id, modifier_id) VALUES (1, 1)"
            )
            await conn.execute(
                "INSERT INTO menu_item_modifiers (menu_item_id, modifier_id) VALUES (1, 2)"
            )
            await conn.commit()

        modifiers = await db.get_menu_item_modifiers(menu_item_id=1)

        assert len(modifiers) == 2
        assert all(m["category"] == "syrup" for m in modifiers)


@pytest.mark.asyncio
class TestGetModifiersByIds:
    """Тесты get_modifiers_by_ids."""

    async def test_get_modifiers_by_ids_empty_list(self, test_db):
        """Пустой список ID возвращает пустой список."""
        result = await db.get_modifiers_by_ids([])

        assert result == []

    async def test_get_modifiers_by_ids_returns_matching(self, test_db, sample_modifiers):
        """Возвращает модификаторы по указанным ID."""
        async with aiosqlite.connect(test_db) as conn:
            for mod in sample_modifiers:
                await conn.execute(
                    "INSERT INTO modifiers (id, name, category, price, is_available) VALUES (?, ?, ?, ?, 1)",
                    (mod["id"], mod["name"], mod["category"], mod["price"])
                )
            await conn.commit()

        result = await db.get_modifiers_by_ids([1, 3])

        assert len(result) == 2
        ids = {m["id"] for m in result}
        assert ids == {1, 3}


@pytest.mark.asyncio
class TestGetMenuItemSizes:
    """Тесты get_menu_item_sizes."""

    async def test_get_menu_item_sizes_empty(self, populated_db):
        """Позиция без размеров возвращает пустой список."""
        sizes = await db.get_menu_item_sizes(menu_item_id=1)

        assert sizes == []

    async def test_get_menu_item_sizes_returns_sizes(self, populated_db, sample_sizes):
        """Возвращает размеры для позиции."""
        async with aiosqlite.connect(populated_db) as conn:
            for size in sample_sizes:
                await conn.execute(
                    "INSERT INTO menu_item_sizes (menu_item_id, size, size_name, price_diff, available) VALUES (1, ?, ?, ?, 1)",
                    (size["size"], size["size_name"], size["price_diff"])
                )
            await conn.commit()

        sizes = await db.get_menu_item_sizes(menu_item_id=1)

        assert len(sizes) == 3
        assert sizes[0]["size"] == "S"  # отсортировано по price_diff ASC
