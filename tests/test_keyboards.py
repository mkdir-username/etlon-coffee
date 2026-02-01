"""Unit тесты для модуля bot/keyboards.py."""
import pytest

from bot.models import CartItem, MenuItem, Order, OrderItem, OrderStatus
from bot.keyboards import (
    menu_keyboard,
    cart_keyboard,
    size_keyboard,
    modifiers_keyboard,
    bonus_keyboard,
    history_keyboard,
    favorites_keyboard,
    barista_orders_keyboard,
    barista_order_detail_keyboard,
    order_detail_keyboard,
    pickup_time_keyboard,
    confirm_keyboard,
    menu_manage_keyboard,
    menu_item_detail_keyboard,
)


class TestMenuKeyboard:
    """Тесты клавиатуры меню."""

    def test_empty_menu_returns_empty_keyboard(self):
        """Пустое меню возвращает клавиатуру без кнопок."""
        kb = menu_keyboard([], [], None)
        assert kb.inline_keyboard == []

    def test_menu_with_items_creates_buttons(self, sample_menu_items: list[dict]):
        """Меню с позициями создаёт кнопки с корректным callback_data."""
        items = [MenuItem(**m) for m in sample_menu_items[:3]]
        kb = menu_keyboard(items, [], None)

        assert len(kb.inline_keyboard) == 3
        assert kb.inline_keyboard[0][0].callback_data == "menu:1"
        assert kb.inline_keyboard[1][0].callback_data == "menu:2"
        assert kb.inline_keyboard[2][0].callback_data == "menu:3"

    def test_menu_shows_item_name_and_price(self, sample_menu_items: list[dict]):
        """Кнопки содержат название и цену позиции."""
        items = [MenuItem(**sample_menu_items[0])]  # Эспрессо, 120р
        kb = menu_keyboard(items, [], None)

        button_text = kb.inline_keyboard[0][0].text
        assert "Эспрессо" in button_text
        assert "120р" in button_text

    def test_menu_shows_cart_count_for_item_in_cart(self, sample_menu_items: list[dict]):
        """Позиция в корзине показывает количество в квадратных скобках."""
        items = [MenuItem(**sample_menu_items[0])]  # id=1
        cart = [CartItem(menu_item_id=1, name="Эспрессо", price=120, quantity=2)]

        kb = menu_keyboard(items, cart, None)

        button_text = kb.inline_keyboard[0][0].text
        assert "[2]" in button_text

    def test_menu_shows_favorite_marker(self, sample_menu_items: list[dict]):
        """Позиция в избранном показывает звёздочку."""
        items = [MenuItem(**sample_menu_items[0])]  # id=1
        favorite_ids = {1}

        kb = menu_keyboard(items, [], favorite_ids)

        button_text = kb.inline_keyboard[0][0].text
        assert "*" in button_text

    def test_menu_shows_cart_button_when_cart_not_empty(self, sample_menu_items: list[dict]):
        """Непустая корзина добавляет кнопку 'Корзина' с общей суммой."""
        items = [MenuItem(**sample_menu_items[0])]
        cart = [CartItem(menu_item_id=1, name="Эспрессо", price=120, quantity=2)]

        kb = menu_keyboard(items, cart, None)

        # Последний ряд — кнопка корзины
        last_row = kb.inline_keyboard[-1]
        assert len(last_row) == 1
        assert last_row[0].callback_data == "cart:show"
        assert "240р" in last_row[0].text  # 120 * 2

    def test_menu_no_cart_button_when_cart_empty(self, sample_menu_items: list[dict]):
        """Пустая корзина не добавляет кнопку 'Корзина'."""
        items = [MenuItem(**sample_menu_items[0])]

        kb = menu_keyboard(items, [], None)

        # Только одна кнопка — позиция меню
        assert len(kb.inline_keyboard) == 1
        assert kb.inline_keyboard[0][0].callback_data == "menu:1"

    def test_menu_combines_cart_count_and_favorite(self, sample_menu_items: list[dict]):
        """Позиция может иметь одновременно маркер избранного и счётчик корзины."""
        items = [MenuItem(**sample_menu_items[0])]  # id=1
        cart = [CartItem(menu_item_id=1, name="Эспрессо", price=120, quantity=3)]
        favorite_ids = {1}

        kb = menu_keyboard(items, cart, favorite_ids)

        button_text = kb.inline_keyboard[0][0].text
        assert "*" in button_text
        assert "[3]" in button_text


class TestCartKeyboard:
    """Тесты клавиатуры корзины."""

    def test_single_item_creates_row_with_controls(self):
        """Одна позиция создаёт ряд с кнопками +/-/комментарий."""
        cart = [CartItem(menu_item_id=1, name="Эспрессо", price=120, quantity=1)]

        kb = cart_keyboard(cart)

        # Первый ряд — кнопки для позиции
        item_row = kb.inline_keyboard[0]
        assert len(item_row) == 4  # -, название, +, комментарий

        assert item_row[0].text == "−"
        assert "cart:dec:" in item_row[0].callback_data

        assert "Эспрессо" in item_row[1].text
        assert "x1" in item_row[1].text

        assert item_row[2].text == "+"
        assert "cart:inc:" in item_row[2].callback_data

    def test_item_with_size_shows_size_in_name(self):
        """Позиция с размером показывает размер в названии."""
        cart = [CartItem(
            menu_item_id=3,
            name="Латте",
            price=260,
            quantity=1,
            size="M",
        )]

        kb = cart_keyboard(cart)

        name_button = kb.inline_keyboard[0][1]
        assert "(M)" in name_button.text

    def test_item_with_modifiers_shows_plus_indicator(self):
        """Позиция с модификаторами показывает индикатор '+'."""
        cart = [CartItem(
            menu_item_id=3,
            name="Латте",
            price=260,
            quantity=1,
            modifier_ids=[1, 2],
        )]

        kb = cart_keyboard(cart)

        name_button = kb.inline_keyboard[0][1]
        # " +" в конце названия
        assert "Латте +" in name_button.text or name_button.text.endswith(" +")

    def test_item_without_comment_shows_pencil_icon(self):
        """Позиция без комментария показывает иконку карандаша."""
        cart = [CartItem(menu_item_id=1, name="Эспрессо", price=120, quantity=1)]

        kb = cart_keyboard(cart)

        comment_button = kb.inline_keyboard[0][3]
        assert comment_button.text == "✏️"

    def test_item_with_comment_shows_note_icon(self):
        """Позиция с комментарием показывает иконку заметки."""
        cart = [CartItem(
            menu_item_id=1,
            name="Эспрессо",
            price=120,
            quantity=1,
            comment="Без сахара",
        )]

        kb = cart_keyboard(cart)

        comment_button = kb.inline_keyboard[0][3]
        assert comment_button.text == "📝"

    def test_cart_has_menu_and_checkout_buttons(self):
        """Корзина имеет кнопки 'Меню' и 'Оформить'."""
        cart = [CartItem(menu_item_id=1, name="Эспрессо", price=120, quantity=1)]

        kb = cart_keyboard(cart)

        last_row = kb.inline_keyboard[-1]
        assert len(last_row) == 2

        assert last_row[0].callback_data == "cart:back"
        assert "Меню" in last_row[0].text

        assert last_row[1].callback_data == "cart:checkout"
        assert "Оформить" in last_row[1].text

    def test_cart_key_includes_size_and_modifiers(self):
        """callback_data содержит уникальный ключ: id + size + modifiers."""
        cart = [CartItem(
            menu_item_id=3,
            name="Латте",
            price=310,
            quantity=1,
            size="M",
            modifier_ids=[1, 5],
        )]

        kb = cart_keyboard(cart)

        dec_callback = kb.inline_keyboard[0][0].callback_data
        # Формат: cart:dec:3:M:1-5
        assert "cart:dec:3:M:" in dec_callback
        assert "1-5" in dec_callback or "5-1" not in dec_callback  # отсортированы


class TestSizeKeyboard:
    """Тесты клавиатуры выбора размера."""

    def test_creates_button_for_each_size(self, sample_sizes: list[dict]):
        """Создаёт кнопку для каждого размера."""
        kb = size_keyboard(
            menu_item_id=3,
            item_name="Латте",
            base_price=220,
            sizes=sample_sizes,
        )

        # 3 размера + кнопка "Назад"
        assert len(kb.inline_keyboard) == 4

    def test_callback_data_format(self, sample_sizes: list[dict]):
        """callback_data в формате size:{id}:{S/M/L}."""
        kb = size_keyboard(
            menu_item_id=3,
            item_name="Латте",
            base_price=220,
            sizes=sample_sizes,
        )

        assert kb.inline_keyboard[0][0].callback_data == "size:3:S"
        assert kb.inline_keyboard[1][0].callback_data == "size:3:M"
        assert kb.inline_keyboard[2][0].callback_data == "size:3:L"

    def test_shows_final_price(self, sample_sizes: list[dict]):
        """Кнопка показывает итоговую цену с учётом надбавки."""
        kb = size_keyboard(
            menu_item_id=3,
            item_name="Латте",
            base_price=220,
            sizes=sample_sizes,
        )

        # S: 220р, M: 260р, L: 300р
        assert "220р" in kb.inline_keyboard[0][0].text
        assert "260р" in kb.inline_keyboard[1][0].text
        assert "300р" in kb.inline_keyboard[2][0].text

    def test_shows_diff_for_non_zero(self, sample_sizes: list[dict]):
        """Кнопка показывает +Xр для ненулевых надбавок."""
        kb = size_keyboard(
            menu_item_id=3,
            item_name="Латте",
            base_price=220,
            sizes=sample_sizes,
        )

        # S: без надбавки
        assert "+0р" not in kb.inline_keyboard[0][0].text

        # M: +40р
        assert "+40р" in kb.inline_keyboard[1][0].text

        # L: +80р
        assert "+80р" in kb.inline_keyboard[2][0].text

    def test_has_back_button(self, sample_sizes: list[dict]):
        """Имеет кнопку 'Назад'."""
        kb = size_keyboard(
            menu_item_id=3,
            item_name="Латте",
            base_price=220,
            sizes=sample_sizes,
        )

        last_row = kb.inline_keyboard[-1]
        assert last_row[0].callback_data == "size:back"
        assert "Назад" in last_row[0].text


class TestModifiersKeyboard:
    """Тесты клавиатуры модификаторов."""

    def test_groups_by_category(self, sample_modifiers: list[dict]):
        """Модификаторы группируются по категориям."""
        kb = modifiers_keyboard(
            menu_item_id=3,
            size="M",
            modifiers=sample_modifiers,
            selected_ids=[],
        )

        # Ищем заголовки категорий
        category_buttons = [
            btn.text for row in kb.inline_keyboard for btn in row
            if "—" in btn.text and ("Сиропы" in btn.text or "Молоко" in btn.text or "Дополнительно" in btn.text)
        ]

        assert len(category_buttons) == 3

    def test_selected_shows_checkmark(self, sample_modifiers: list[dict]):
        """Выбранный модификатор показывает галочку."""
        kb = modifiers_keyboard(
            menu_item_id=3,
            size="M",
            modifiers=sample_modifiers,
            selected_ids=[1],  # Ванильный сироп
        )

        # Ищем кнопку с ванильным сиропом
        vanilla_btn = None
        for row in kb.inline_keyboard:
            for btn in row:
                if "Ванильный" in btn.text:
                    vanilla_btn = btn
                    break

        assert vanilla_btn is not None
        assert "✓" in vanilla_btn.text

    def test_unselected_shows_circle(self, sample_modifiers: list[dict]):
        """Невыбранный модификатор показывает кружок."""
        kb = modifiers_keyboard(
            menu_item_id=3,
            size="M",
            modifiers=sample_modifiers,
            selected_ids=[],
        )

        # Ищем кнопку с ванильным сиропом
        vanilla_btn = None
        for row in kb.inline_keyboard:
            for btn in row:
                if "Ванильный" in btn.text:
                    vanilla_btn = btn
                    break

        assert vanilla_btn is not None
        assert "○" in vanilla_btn.text

    def test_callback_data_format(self, sample_modifiers: list[dict]):
        """callback_data в формате mod:toggle:{id}:{size}:{modifier_id}."""
        kb = modifiers_keyboard(
            menu_item_id=3,
            size="M",
            modifiers=sample_modifiers,
            selected_ids=[],
        )

        # Ищем кнопку модификатора
        mod_btn = None
        for row in kb.inline_keyboard:
            for btn in row:
                if "mod:toggle:" in btn.callback_data:
                    mod_btn = btn
                    break
            if mod_btn:
                break

        assert mod_btn is not None
        # Формат: mod:toggle:3:M:1
        parts = mod_btn.callback_data.split(":")
        assert parts[0] == "mod"
        assert parts[1] == "toggle"
        assert parts[2] == "3"  # menu_item_id
        assert parts[3] == "M"  # size

    def test_done_button_shows_total_price(self, sample_modifiers: list[dict]):
        """Кнопка 'Готово' показывает сумму выбранных модификаторов."""
        kb = modifiers_keyboard(
            menu_item_id=3,
            size="M",
            modifiers=sample_modifiers,
            selected_ids=[1, 3],  # Ванильный (50) + Овсяное (60) = 110
        )

        # Ищем кнопку "Готово"
        done_btn = None
        for row in kb.inline_keyboard:
            for btn in row:
                if "Готово" in btn.text:
                    done_btn = btn
                    break

        assert done_btn is not None
        assert "+110₽" in done_btn.text

    def test_done_button_without_modifiers(self, sample_modifiers: list[dict]):
        """Кнопка 'Готово' без выбранных модификаторов не показывает цену."""
        kb = modifiers_keyboard(
            menu_item_id=3,
            size="M",
            modifiers=sample_modifiers,
            selected_ids=[],
        )

        done_btn = None
        for row in kb.inline_keyboard:
            for btn in row:
                if "Готово" in btn.text:
                    done_btn = btn
                    break

        assert done_btn is not None
        assert "Готово →" == done_btn.text

    def test_has_back_and_done_buttons(self, sample_modifiers: list[dict]):
        """Имеет кнопки 'Назад' и 'Готово'."""
        kb = modifiers_keyboard(
            menu_item_id=3,
            size="M",
            modifiers=sample_modifiers,
            selected_ids=[],
        )

        last_row = kb.inline_keyboard[-1]
        assert len(last_row) == 2

        back_btn = last_row[0]
        done_btn = last_row[1]

        assert "mod:back:3" == back_btn.callback_data
        assert "mod:done:3:M" == done_btn.callback_data

    def test_handles_none_size(self, sample_modifiers: list[dict]):
        """Корректно обрабатывает size=None."""
        kb = modifiers_keyboard(
            menu_item_id=3,
            size=None,
            modifiers=sample_modifiers,
            selected_ids=[],
        )

        # size заменяется на "none" в callback_data
        done_btn = None
        for row in kb.inline_keyboard:
            for btn in row:
                if "Готово" in btn.text:
                    done_btn = btn
                    break

        assert done_btn is not None
        assert "mod:done:3:none" == done_btn.callback_data


class TestBonusKeyboard:
    """Тесты клавиатуры списания баллов."""

    def test_shows_available_fixed_amounts(self):
        """Показывает только доступные фиксированные суммы."""
        kb = bonus_keyboard(user_points=200, max_redeem=150, order_total=500)

        # Доступны: 50, 100, 150 (но не 200, т.к. max_redeem=150)
        button_texts = [btn.text for row in kb.inline_keyboard for btn in row]

        assert any("50" in t for t in button_texts)
        assert any("100" in t for t in button_texts)
        assert any("150" in t for t in button_texts)

    def test_shows_max_button_when_different(self):
        """Показывает кнопку 'Максимум' если max_redeem не в фиксированных."""
        kb = bonus_keyboard(user_points=200, max_redeem=175, order_total=500)

        button_texts = [btn.text for row in kb.inline_keyboard for btn in row]
        max_btn = [t for t in button_texts if "Максимум" in t]

        assert len(max_btn) == 1
        assert "175" in max_btn[0]

    def test_no_max_button_when_in_fixed(self):
        """Не показывает кнопку 'Максимум' если max_redeem есть в фиксированных."""
        kb = bonus_keyboard(user_points=200, max_redeem=100, order_total=500)

        button_texts = [btn.text for row in kb.inline_keyboard for btn in row]
        max_btn = [t for t in button_texts if "Максимум" in t]

        assert len(max_btn) == 0

    def test_always_has_skip_button(self):
        """Всегда есть кнопка 'Пропустить'."""
        kb = bonus_keyboard(user_points=200, max_redeem=150, order_total=500)

        last_row = kb.inline_keyboard[-1]
        assert any("Пропустить" in btn.text for btn in last_row)
        assert any(btn.callback_data == "bonus:skip" for btn in last_row)

    def test_callback_data_for_fixed_amounts(self):
        """callback_data для фиксированных сумм в формате bonus:use:{amount}."""
        kb = bonus_keyboard(user_points=200, max_redeem=150, order_total=500)

        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]

        assert "bonus:use:50" in callbacks
        assert "bonus:use:100" in callbacks
        assert "bonus:use:150" in callbacks

    def test_callback_data_for_max(self):
        """callback_data для максимума: bonus:max."""
        kb = bonus_keyboard(user_points=200, max_redeem=175, order_total=500)

        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "bonus:max" in callbacks

    def test_respects_user_points_limit(self):
        """Не показывает суммы превышающие баланс пользователя."""
        kb = bonus_keyboard(user_points=75, max_redeem=200, order_total=500)

        button_texts = [btn.text for row in kb.inline_keyboard for btn in row]

        # Только 50 доступно (75 < 100)
        amount_buttons = [t for t in button_texts if "Списать" in t]
        assert len(amount_buttons) == 1
        assert "50" in amount_buttons[0]


class TestHistoryKeyboard:
    """Тесты клавиатуры истории заказов."""

    def test_creates_button_for_each_order(self, sample_order: Order):
        """Создаёт кнопку для каждого заказа."""
        orders = [sample_order]

        kb = history_keyboard(orders, page=0, has_next=False)

        # Одна кнопка для заказа
        assert len(kb.inline_keyboard) >= 1
        assert f"history:view:{sample_order.id}" == kb.inline_keyboard[0][0].callback_data

    def test_shows_order_summary(self, sample_order: Order):
        """Показывает краткую информацию о заказе."""
        orders = [sample_order]

        kb = history_keyboard(orders, page=0, has_next=False)

        button_text = kb.inline_keyboard[0][0].text

        assert f"#{sample_order.id}" in button_text
        assert f"{sample_order.total}р" in button_text

    def test_first_page_shows_only_next(self, sample_order: Order):
        """Первая страница показывает только кнопку '→'."""
        orders = [sample_order]

        kb = history_keyboard(orders, page=0, has_next=True)

        # Последний ряд — навигация
        nav_row = kb.inline_keyboard[-1]
        nav_callbacks = [btn.callback_data for btn in nav_row]

        assert "history:page:1" in nav_callbacks  # →
        assert "history:page:-1" not in nav_callbacks  # нет ←

    def test_middle_page_shows_both_arrows(self, sample_order: Order):
        """Средняя страница показывает обе стрелки."""
        orders = [sample_order]

        kb = history_keyboard(orders, page=1, has_next=True)

        nav_row = kb.inline_keyboard[-1]
        nav_callbacks = [btn.callback_data for btn in nav_row]

        assert "history:page:0" in nav_callbacks  # ←
        assert "history:page:2" in nav_callbacks  # →

    def test_last_page_shows_only_prev(self, sample_order: Order):
        """Последняя страница показывает только кнопку '←'."""
        orders = [sample_order]

        kb = history_keyboard(orders, page=2, has_next=False)

        nav_row = kb.inline_keyboard[-1]
        nav_callbacks = [btn.callback_data for btn in nav_row]

        assert "history:page:1" in nav_callbacks  # ←
        assert "history:page:3" not in nav_callbacks  # нет →

    def test_single_page_no_navigation(self, sample_order: Order):
        """Единственная страница не показывает навигацию."""
        orders = [sample_order]

        kb = history_keyboard(orders, page=0, has_next=False)

        # Только кнопки заказов, без навигации
        all_callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert not any("history:page:" in cb for cb in all_callbacks)


class TestFavoritesKeyboard:
    """Тесты клавиатуры избранного."""

    def test_creates_row_for_each_item(self, sample_menu_items: list[dict]):
        """Создаёт ряд для каждой позиции."""
        items = [MenuItem(**sample_menu_items[0]), MenuItem(**sample_menu_items[1])]

        kb = favorites_keyboard(items)

        # 2 позиции + кнопка "Новый заказ"
        assert len(kb.inline_keyboard) == 3

    def test_row_has_add_info_remove_buttons(self, sample_menu_items: list[dict]):
        """Ряд содержит кнопки +, название, x."""
        items = [MenuItem(**sample_menu_items[0])]

        kb = favorites_keyboard(items)

        item_row = kb.inline_keyboard[0]
        assert len(item_row) == 3

        assert item_row[0].text == "+"
        assert "fav:order:1" == item_row[0].callback_data

        assert "Эспрессо" in item_row[1].text
        assert "fav:info:1" == item_row[1].callback_data

        assert item_row[2].text == "x"
        assert "fav:remove:1" == item_row[2].callback_data

    def test_has_new_order_button(self, sample_menu_items: list[dict]):
        """Имеет кнопку 'Новый заказ'."""
        items = [MenuItem(**sample_menu_items[0])]

        kb = favorites_keyboard(items)

        last_row = kb.inline_keyboard[-1]
        assert any("fav:start" == btn.callback_data for btn in last_row)


class TestBaristaOrdersKeyboard:
    """Тесты клавиатуры списка заказов для баристы."""

    def test_empty_orders_shows_refresh(self):
        """Пустой список показывает кнопку 'Нет активных заказов'."""
        kb = barista_orders_keyboard([])

        # Кнопка "Нет активных" + "Обновить"
        assert len(kb.inline_keyboard) == 2
        assert "barista:refresh" == kb.inline_keyboard[0][0].callback_data

    def test_creates_button_for_each_order(self, sample_order: Order):
        """Создаёт кнопку для каждого заказа."""
        orders = [sample_order]

        kb = barista_orders_keyboard(orders)

        assert f"barista:order:{sample_order.id}" == kb.inline_keyboard[0][0].callback_data

    def test_shows_order_id_and_time(self, sample_order: Order):
        """Показывает ID и время забора."""
        orders = [sample_order]

        kb = barista_orders_keyboard(orders)

        button_text = kb.inline_keyboard[0][0].text
        assert f"#{sample_order.id}" in button_text
        assert sample_order.pickup_time in button_text

    def test_has_refresh_button(self, sample_order: Order):
        """Имеет кнопку 'Обновить'."""
        orders = [sample_order]

        kb = barista_orders_keyboard(orders)

        last_row = kb.inline_keyboard[-1]
        assert any("barista:refresh" == btn.callback_data for btn in last_row)


class TestBaristaOrderDetailKeyboard:
    """Тесты клавиатуры деталей заказа для баристы."""

    def test_confirmed_shows_start_preparing(self, sample_order: Order):
        """Статус CONFIRMED показывает кнопку 'Начать готовить'."""
        order = sample_order.model_copy(update={"status": OrderStatus.CONFIRMED})

        kb = barista_order_detail_keyboard(order)

        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert f"barista:status:{order.id}:preparing" in callbacks

    def test_preparing_shows_ready(self, sample_order: Order):
        """Статус PREPARING показывает кнопку 'Готов к выдаче'."""
        order = sample_order.model_copy(update={"status": OrderStatus.PREPARING})

        kb = barista_order_detail_keyboard(order)

        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert f"barista:status:{order.id}:ready" in callbacks

    def test_ready_shows_completed(self, sample_order: Order):
        """Статус READY показывает кнопку 'Выдан'."""
        order = sample_order.model_copy(update={"status": OrderStatus.READY})

        kb = barista_order_detail_keyboard(order)

        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert f"barista:status:{order.id}:completed" in callbacks

    def test_has_back_to_list_button(self, sample_order: Order):
        """Имеет кнопку 'К списку'."""
        kb = barista_order_detail_keyboard(sample_order)

        last_row = kb.inline_keyboard[-1]
        assert any("barista:list" == btn.callback_data for btn in last_row)


class TestOrderDetailKeyboard:
    """Тесты клавиатуры деталей заказа клиента."""

    def test_always_has_repeat_button(self, sample_order: Order):
        """Всегда имеет кнопку 'Повторить заказ'."""
        kb = order_detail_keyboard(order_id=1, order=sample_order, user_id=123456)

        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "repeat:1" in callbacks

    def test_confirmed_owner_has_cancel_button(self, sample_order: Order):
        """Владелец CONFIRMED заказа видит кнопку 'Отменить'."""
        order = sample_order.model_copy(update={"status": OrderStatus.CONFIRMED})

        kb = order_detail_keyboard(order_id=1, order=order, user_id=123456)

        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "cancel:1" in callbacks

    def test_non_owner_no_cancel_button(self, sample_order: Order):
        """Не владелец не видит кнопку 'Отменить'."""
        order = sample_order.model_copy(update={"status": OrderStatus.CONFIRMED})

        kb = order_detail_keyboard(order_id=1, order=order, user_id=999999)  # другой user

        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "cancel:1" not in callbacks

    def test_non_confirmed_no_cancel_button(self, sample_order: Order):
        """Не CONFIRMED статус не показывает кнопку 'Отменить'."""
        order = sample_order.model_copy(update={"status": OrderStatus.PREPARING})

        kb = order_detail_keyboard(order_id=1, order=order, user_id=123456)

        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "cancel:1" not in callbacks

    def test_has_back_to_list_button(self, sample_order: Order):
        """Имеет кнопку 'К списку'."""
        kb = order_detail_keyboard(order_id=1, order=sample_order, user_id=123456)

        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "history:back" in callbacks


class TestPickupTimeKeyboard:
    """Тесты клавиатуры выбора времени."""

    def test_has_time_options(self):
        """Имеет варианты времени."""
        kb = pickup_time_keyboard()

        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]

        assert "time:10" in callbacks
        assert "time:15" in callbacks
        assert "time:20" in callbacks
        assert "time:30" in callbacks

    def test_has_back_button(self):
        """Имеет кнопку 'Назад'."""
        kb = pickup_time_keyboard()

        last_row = kb.inline_keyboard[-1]
        assert any("time:back" == btn.callback_data for btn in last_row)


class TestConfirmKeyboard:
    """Тесты клавиатуры подтверждения."""

    def test_has_edit_and_confirm_buttons(self):
        """Имеет кнопки 'Изменить' и 'Подтвердить'."""
        kb = confirm_keyboard()

        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]

        assert "confirm:edit" in callbacks
        assert "confirm:yes" in callbacks


class TestMenuManageKeyboard:
    """Тесты клавиатуры управления меню."""

    def test_shows_available_with_checkmark(self, sample_menu_items: list[dict]):
        """Доступная позиция показывает галочку."""
        items = [MenuItem(**sample_menu_items[0])]  # available=True

        kb = menu_manage_keyboard(items)

        button_text = kb.inline_keyboard[0][0].text
        assert "✅" in button_text

    def test_shows_unavailable_with_cross(self, sample_menu_items: list[dict]):
        """Недоступная позиция показывает крестик."""
        items = [MenuItem(**sample_menu_items[4])]  # available=False

        kb = menu_manage_keyboard(items)

        button_text = kb.inline_keyboard[0][0].text
        assert "❌" in button_text
        assert "(скрыто)" in button_text

    def test_callback_data_for_toggle(self, sample_menu_items: list[dict]):
        """callback_data для переключения: menu_toggle:{id}."""
        items = [MenuItem(**sample_menu_items[0])]

        kb = menu_manage_keyboard(items)

        assert "menu_toggle:1" == kb.inline_keyboard[0][0].callback_data

    def test_has_refresh_button(self, sample_menu_items: list[dict]):
        """Имеет кнопку 'Обновить'."""
        items = [MenuItem(**sample_menu_items[0])]

        kb = menu_manage_keyboard(items)

        last_row = kb.inline_keyboard[-1]
        assert any("menu_manage:refresh" == btn.callback_data for btn in last_row)


class TestMenuItemDetailKeyboard:
    """Тесты клавиатуры деталей позиции меню."""

    def test_favorite_shows_remove_button(self):
        """Избранная позиция показывает 'Убрать из избранного'."""
        kb = menu_item_detail_keyboard(item_id=1, is_favorite=True)

        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "fav:remove:1" in callbacks

    def test_not_favorite_shows_add_button(self):
        """Не избранная позиция показывает 'Добавить в избранное'."""
        kb = menu_item_detail_keyboard(item_id=1, is_favorite=False)

        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "fav:add:1" in callbacks

    def test_has_back_button(self):
        """Имеет кнопку 'Назад'."""
        kb = menu_item_detail_keyboard(item_id=1, is_favorite=False)

        last_row = kb.inline_keyboard[-1]
        assert any("menu:back" == btn.callback_data for btn in last_row)
