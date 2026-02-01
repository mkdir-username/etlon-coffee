"""Unit-тесты для модуля bot/models.py."""
import json
from datetime import datetime

import pytest
from pydantic import ValidationError

from bot.models import (
    CartItem,
    MenuItem,
    Modifier,
    Order,
    OrderItem,
    OrderStatus,
)


class TestOrderStatus:
    """Тесты для OrderStatus enum."""

    def test_display_name_pending(self):
        """display_name для PENDING."""
        assert OrderStatus.PENDING.display_name == "Ожидает"

    def test_display_name_confirmed(self):
        """display_name для CONFIRMED."""
        assert OrderStatus.CONFIRMED.display_name == "Подтверждён"

    def test_display_name_preparing(self):
        """display_name для PREPARING."""
        assert OrderStatus.PREPARING.display_name == "Готовится"

    def test_display_name_ready(self):
        """display_name для READY."""
        assert OrderStatus.READY.display_name == "Готов"

    def test_display_name_completed(self):
        """display_name для COMPLETED."""
        assert OrderStatus.COMPLETED.display_name == "Выдан"

    def test_display_name_cancelled(self):
        """display_name для CANCELLED."""
        assert OrderStatus.CANCELLED.display_name == "Отменён"

    def test_is_str_enum(self):
        """OrderStatus наследует str, можно сравнивать со строками."""
        assert OrderStatus.PENDING == "pending"
        assert OrderStatus.CONFIRMED == "confirmed"
        assert OrderStatus.PREPARING == "preparing"
        assert OrderStatus.READY == "ready"
        assert OrderStatus.COMPLETED == "completed"
        assert OrderStatus.CANCELLED == "cancelled"

    def test_value_attribute(self):
        """Проверка атрибута value."""
        assert OrderStatus.PENDING.value == "pending"
        assert OrderStatus.CONFIRMED.value == "confirmed"

    def test_create_from_string(self):
        """Создание статуса из строки."""
        status = OrderStatus("confirmed")
        assert status == OrderStatus.CONFIRMED
        assert status.display_name == "Подтверждён"

    def test_invalid_status_raises(self):
        """Недопустимое значение вызывает ValueError."""
        with pytest.raises(ValueError):
            OrderStatus("invalid_status")

    def test_all_statuses_have_display_name(self):
        """Все статусы имеют display_name."""
        for status in OrderStatus:
            assert status.display_name is not None
            assert isinstance(status.display_name, str)
            assert len(status.display_name) > 0


class TestMenuItem:
    """Тесты для MenuItem."""

    def test_create_minimal(self):
        """Создание с минимальными полями."""
        item = MenuItem(id=1, name="Латте", price=220)
        assert item.id == 1
        assert item.name == "Латте"
        assert item.price == 220
        assert item.available is True

    def test_default_available_true(self):
        """Дефолтное значение available=True."""
        item = MenuItem(id=1, name="Эспрессо", price=120)
        assert item.available is True

    def test_create_unavailable_item(self):
        """Создание недоступной позиции."""
        item = MenuItem(id=5, name="Раф", price=280, available=False)
        assert item.available is False

    def test_price_as_int(self):
        """Цена сохраняется как int."""
        item = MenuItem(id=1, name="Американо", price=150)
        assert isinstance(item.price, int)

    def test_price_coerced_from_float(self):
        """Pydantic конвертирует float в int для price."""
        item = MenuItem(id=1, name="Капучино", price=200.0)
        assert item.price == 200
        assert isinstance(item.price, int)

    def test_missing_required_field_raises(self):
        """Отсутствие обязательного поля вызывает ValidationError."""
        with pytest.raises(ValidationError):
            MenuItem(id=1, name="Латте")  # price отсутствует

    def test_invalid_type_raises(self):
        """Неправильный тип поля вызывает ValidationError."""
        with pytest.raises(ValidationError):
            MenuItem(id="abc", name="Латте", price=220)  # id должен быть int

    def test_model_dump(self):
        """Сериализация в dict."""
        item = MenuItem(id=1, name="Латте", price=220)
        data = item.model_dump()
        assert data == {
            "id": 1,
            "name": "Латте",
            "price": 220,
            "available": True,
        }

    def test_model_validate(self):
        """Десериализация из dict."""
        data = {"id": 2, "name": "Американо", "price": 150, "available": False}
        item = MenuItem.model_validate(data)
        assert item.id == 2
        assert item.name == "Американо"
        assert item.price == 150
        assert item.available is False


class TestModifier:
    """Тесты для Modifier."""

    def test_create_minimal(self):
        """Создание с минимальными полями."""
        modifier = Modifier(id=1, name="Ванильный сироп", category="syrup")
        assert modifier.id == 1
        assert modifier.name == "Ванильный сироп"
        assert modifier.category == "syrup"

    def test_default_values(self):
        """Дефолтные значения: price=0, is_available=True, sort_order=0."""
        modifier = Modifier(id=1, name="Ванильный сироп", category="syrup")
        assert modifier.price == 0
        assert modifier.is_available is True
        assert modifier.sort_order == 0

    def test_create_with_all_fields(self):
        """Создание со всеми полями."""
        modifier = Modifier(
            id=3,
            name="Овсяное молоко",
            category="milk",
            price=60,
            is_available=True,
            sort_order=5,
        )
        assert modifier.id == 3
        assert modifier.name == "Овсяное молоко"
        assert modifier.category == "milk"
        assert modifier.price == 60
        assert modifier.is_available is True
        assert modifier.sort_order == 5

    def test_unavailable_modifier(self):
        """Создание недоступного модификатора."""
        modifier = Modifier(
            id=10,
            name="Лавандовый сироп",
            category="syrup",
            is_available=False,
        )
        assert modifier.is_available is False

    def test_model_dump(self):
        """Сериализация в dict."""
        modifier = Modifier(id=1, name="Двойной шот", category="extra", price=80)
        data = modifier.model_dump()
        assert data == {
            "id": 1,
            "name": "Двойной шот",
            "category": "extra",
            "price": 80,
            "is_available": True,
            "sort_order": 0,
        }

    def test_missing_category_raises(self):
        """Отсутствие category вызывает ValidationError."""
        with pytest.raises(ValidationError):
            Modifier(id=1, name="Сироп")


class TestOrderItem:
    """Тесты для OrderItem."""

    def test_create_minimal(self):
        """Создание с минимальными обязательными полями."""
        item = OrderItem(menu_item_id=1, name="Эспрессо", price=120)
        assert item.menu_item_id == 1
        assert item.name == "Эспрессо"
        assert item.price == 120

    def test_default_values(self):
        """Проверка всех дефолтных значений."""
        item = OrderItem(menu_item_id=1, name="Эспрессо", price=120)
        assert item.quantity == 1
        assert item.comment is None
        assert item.size is None
        assert item.size_name is None
        assert item.modifier_ids == []
        assert item.modifier_names == []
        assert item.modifiers_price == 0

    def test_create_with_all_fields(self):
        """Создание со всеми полями."""
        item = OrderItem(
            menu_item_id=3,
            name="Латте",
            price=260,
            quantity=2,
            comment="Без сахара",
            size="M",
            size_name="Средний 350мл",
            modifier_ids=[1, 5],
            modifier_names=["Ванильный сироп", "Двойной шот"],
            modifiers_price=130,
        )
        assert item.menu_item_id == 3
        assert item.name == "Латте"
        assert item.price == 260
        assert item.quantity == 2
        assert item.comment == "Без сахара"
        assert item.size == "M"
        assert item.size_name == "Средний 350мл"
        assert item.modifier_ids == [1, 5]
        assert item.modifier_names == ["Ванильный сироп", "Двойной шот"]
        assert item.modifiers_price == 130

    def test_empty_modifier_lists(self):
        """Пустые списки модификаторов."""
        item = OrderItem(
            menu_item_id=1,
            name="Эспрессо",
            price=120,
            modifier_ids=[],
            modifier_names=[],
        )
        assert item.modifier_ids == []
        assert item.modifier_names == []

    def test_model_dump(self):
        """Сериализация в dict."""
        item = OrderItem(menu_item_id=1, name="Эспрессо", price=120, quantity=2)
        data = item.model_dump()
        assert data["menu_item_id"] == 1
        assert data["name"] == "Эспрессо"
        assert data["price"] == 120
        assert data["quantity"] == 2
        assert data["comment"] is None
        assert data["modifier_ids"] == []

    def test_model_validate_from_dict(self):
        """Десериализация из dict."""
        data = {
            "menu_item_id": 3,
            "name": "Латте",
            "price": 220,
            "quantity": 1,
            "size": "L",
            "size_name": "Большой 450мл",
            "modifier_ids": [1],
            "modifier_names": ["Ванильный сироп"],
            "modifiers_price": 50,
        }
        item = OrderItem.model_validate(data)
        assert item.menu_item_id == 3
        assert item.size == "L"
        assert item.modifier_ids == [1]

    def test_json_serialization(self):
        """Сериализация в JSON и обратно."""
        item = OrderItem(
            menu_item_id=1,
            name="Эспрессо",
            price=120,
            comment="Покрепче",
        )
        json_str = item.model_dump_json()
        restored = OrderItem.model_validate_json(json_str)
        assert restored == item


class TestOrder:
    """Тесты для Order."""

    def test_create_minimal(self):
        """Создание заказа с минимальными полями."""
        items = [OrderItem(menu_item_id=1, name="Эспрессо", price=120)]
        order = Order(
            id=1,
            user_id=123456,
            user_name="Test User",
            items=items,
            total=120,
            pickup_time="через 15 мин",
            created_at=datetime(2026, 2, 1, 12, 0, 0),
        )
        assert order.id == 1
        assert order.user_id == 123456
        assert order.user_name == "Test User"
        assert len(order.items) == 1
        assert order.total == 120
        assert order.pickup_time == "через 15 мин"

    def test_default_status_pending(self):
        """Дефолтный статус PENDING."""
        items = [OrderItem(menu_item_id=1, name="Эспрессо", price=120)]
        order = Order(
            id=1,
            user_id=123456,
            user_name="Test User",
            items=items,
            total=120,
            pickup_time="через 15 мин",
            created_at=datetime.now(),
        )
        assert order.status == OrderStatus.PENDING

    def test_create_with_custom_status(self):
        """Создание с кастомным статусом."""
        items = [OrderItem(menu_item_id=1, name="Эспрессо", price=120)]
        order = Order(
            id=1,
            user_id=123456,
            user_name="Test User",
            items=items,
            total=120,
            pickup_time="через 15 мин",
            status=OrderStatus.CONFIRMED,
            created_at=datetime.now(),
        )
        assert order.status == OrderStatus.CONFIRMED

    def test_multiple_items(self):
        """Заказ с несколькими позициями."""
        items = [
            OrderItem(menu_item_id=1, name="Эспрессо", price=120, quantity=2),
            OrderItem(menu_item_id=3, name="Латте", price=220),
        ]
        order = Order(
            id=2,
            user_id=123456,
            user_name="Test User",
            items=items,
            total=460,
            pickup_time="через 30 мин",
            created_at=datetime.now(),
        )
        assert len(order.items) == 2
        assert order.items[0].quantity == 2
        assert order.total == 460

    def test_model_dump(self):
        """Сериализация в dict."""
        items = [OrderItem(menu_item_id=1, name="Эспрессо", price=120)]
        created = datetime(2026, 2, 1, 12, 0, 0)
        order = Order(
            id=1,
            user_id=123456,
            user_name="Test User",
            items=items,
            total=120,
            pickup_time="через 15 мин",
            status=OrderStatus.CONFIRMED,
            created_at=created,
        )
        data = order.model_dump()
        assert data["id"] == 1
        assert data["user_id"] == 123456
        assert data["status"] == "confirmed"  # str Enum value
        assert data["created_at"] == created
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "Эспрессо"

    def test_model_validate(self):
        """Десериализация из dict."""
        data = {
            "id": 5,
            "user_id": 789012,
            "user_name": "Another User",
            "items": [
                {"menu_item_id": 2, "name": "Американо", "price": 150, "quantity": 1}
            ],
            "total": 150,
            "pickup_time": "через 20 мин",
            "status": "preparing",
            "created_at": "2026-02-01T14:30:00",
        }
        order = Order.model_validate(data)
        assert order.id == 5
        assert order.user_name == "Another User"
        assert order.status == OrderStatus.PREPARING
        assert len(order.items) == 1
        assert isinstance(order.items[0], OrderItem)

    def test_json_round_trip(self):
        """Сериализация в JSON и обратно."""
        items = [
            OrderItem(
                menu_item_id=3,
                name="Латте",
                price=260,
                modifier_ids=[1],
                modifier_names=["Ванильный сироп"],
                modifiers_price=50,
            )
        ]
        order = Order(
            id=10,
            user_id=123456,
            user_name="Test User",
            items=items,
            total=310,
            pickup_time="через 15 мин",
            status=OrderStatus.READY,
            created_at=datetime(2026, 2, 1, 15, 0, 0),
        )
        json_str = order.model_dump_json()
        restored = Order.model_validate_json(json_str)
        assert restored.id == order.id
        assert restored.status == order.status
        assert restored.items[0].modifier_ids == [1]

    def test_empty_items_list(self):
        """Заказ с пустым списком позиций (edge case)."""
        order = Order(
            id=1,
            user_id=123456,
            user_name="Test User",
            items=[],
            total=0,
            pickup_time="через 15 мин",
            created_at=datetime.now(),
        )
        assert order.items == []
        assert order.total == 0


class TestCartItem:
    """Тесты для CartItem."""

    def test_create_minimal(self):
        """Создание с минимальными полями."""
        item = CartItem(menu_item_id=1, name="Эспрессо", price=120)
        assert item.menu_item_id == 1
        assert item.name == "Эспрессо"
        assert item.price == 120

    def test_default_values(self):
        """Проверка всех дефолтных значений."""
        item = CartItem(menu_item_id=1, name="Эспрессо", price=120)
        assert item.quantity == 1
        assert item.comment is None
        assert item.size is None
        assert item.size_name is None
        assert item.modifier_ids == []
        assert item.modifier_names == []
        assert item.modifiers_price == 0

    def test_create_with_all_fields(self):
        """Создание со всеми полями."""
        item = CartItem(
            menu_item_id=3,
            name="Латте",
            price=260,
            quantity=2,
            comment="Без сахара",
            size="M",
            size_name="Средний 350мл",
            modifier_ids=[1, 5],
            modifier_names=["Ванильный сироп", "Двойной шот"],
            modifiers_price=130,
        )
        assert item.quantity == 2
        assert item.comment == "Без сахара"
        assert item.modifier_ids == [1, 5]
        assert item.modifiers_price == 130

    def test_from_dict_fsm_state_minimal(self):
        """Конвертация из dict (минимальный формат FSM state)."""
        data = {
            "menu_item_id": 1,
            "name": "Эспрессо",
            "price": 120,
            "quantity": 2,
        }
        item = CartItem.model_validate(data)
        assert item.menu_item_id == 1
        assert item.quantity == 2
        assert item.modifier_ids == []

    def test_from_dict_fsm_state_full(self):
        """Конвертация из dict (полный формат FSM state)."""
        data = {
            "menu_item_id": 3,
            "name": "Латте",
            "price": 260,
            "quantity": 1,
            "size": "M",
            "size_name": "Средний 350мл",
            "modifier_ids": [1],
            "modifier_names": ["Ванильный сироп"],
            "modifiers_price": 50,
        }
        item = CartItem.model_validate(data)
        assert item.size == "M"
        assert item.size_name == "Средний 350мл"
        assert item.modifier_ids == [1]
        assert item.modifiers_price == 50

    def test_model_dump(self):
        """Сериализация в dict."""
        item = CartItem(
            menu_item_id=1,
            name="Эспрессо",
            price=120,
            quantity=3,
        )
        data = item.model_dump()
        assert data["menu_item_id"] == 1
        assert data["quantity"] == 3
        assert data["modifier_ids"] == []

    def test_json_serialization(self):
        """Сериализация в JSON и обратно."""
        item = CartItem(
            menu_item_id=3,
            name="Латте",
            price=260,
            modifier_ids=[1, 2],
            modifier_names=["Ванильный сироп", "Карамельный сироп"],
            modifiers_price=100,
        )
        json_str = item.model_dump_json()
        restored = CartItem.model_validate_json(json_str)
        assert restored == item
        assert restored.modifier_ids == [1, 2]

    def test_cart_item_equals_order_item_structure(self):
        """CartItem и OrderItem имеют одинаковую структуру полей."""
        cart_fields = set(CartItem.model_fields.keys())
        order_fields = set(OrderItem.model_fields.keys())
        assert cart_fields == order_fields


class TestSerializationEdgeCases:
    """Тесты edge cases сериализации."""

    def test_order_with_nested_items_json(self):
        """Сложный заказ с вложенными items в JSON."""
        items = [
            OrderItem(
                menu_item_id=1,
                name="Эспрессо",
                price=120,
                quantity=2,
            ),
            OrderItem(
                menu_item_id=3,
                name="Латте",
                price=260,
                size="M",
                size_name="Средний 350мл",
                modifier_ids=[1, 5],
                modifier_names=["Ванильный сироп", "Двойной шот"],
                modifiers_price=130,
            ),
        ]
        order = Order(
            id=100,
            user_id=123456,
            user_name="Complex User",
            items=items,
            total=630,
            pickup_time="через 30 мин",
            status=OrderStatus.CONFIRMED,
            created_at=datetime(2026, 2, 1, 16, 30, 0),
        )

        json_str = order.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["id"] == 100
        assert len(parsed["items"]) == 2
        assert parsed["items"][1]["modifier_ids"] == [1, 5]

        restored = Order.model_validate_json(json_str)
        assert restored.items[0].quantity == 2
        assert restored.items[1].modifier_names == ["Ванильный сироп", "Двойной шот"]

    def test_unicode_in_names(self):
        """Кириллица и спецсимволы в названиях."""
        item = MenuItem(id=1, name="Кофе «Раф»", price=280)
        data = item.model_dump()
        assert data["name"] == "Кофе «Раф»"

        json_str = item.model_dump_json()
        restored = MenuItem.model_validate_json(json_str)
        assert restored.name == "Кофе «Раф»"

    def test_empty_string_comment(self):
        """Пустая строка как комментарий (не None)."""
        item = CartItem(
            menu_item_id=1,
            name="Эспрессо",
            price=120,
            comment="",
        )
        assert item.comment == ""
        assert item.comment is not None

    def test_zero_price_modifier(self):
        """Модификатор с нулевой ценой."""
        modifier = Modifier(id=1, name="Без сахара", category="extra", price=0)
        assert modifier.price == 0

    def test_large_quantity(self):
        """Большое количество позиций."""
        item = OrderItem(menu_item_id=1, name="Эспрессо", price=120, quantity=99)
        assert item.quantity == 99

    def test_datetime_serialization_format(self):
        """Формат сериализации datetime."""
        order = Order(
            id=1,
            user_id=123,
            user_name="User",
            items=[OrderItem(menu_item_id=1, name="Test", price=100)],
            total=100,
            pickup_time="через 15 мин",
            created_at=datetime(2026, 2, 1, 12, 30, 45),
        )
        json_str = order.model_dump_json()
        # Pydantic использует ISO формат
        assert "2026-02-01" in json_str
        assert "12:30:45" in json_str
