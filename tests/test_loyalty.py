"""Unit тесты для модуля bot/loyalty.py."""
import pytest
import aiosqlite

from bot import loyalty
from bot.loyalty import (
    POINTS_PER_100_RUB,
    MAX_REDEEM_PERCENT,
    STAMPS_FOR_FREE_DRINK,
    accrue_points,
    calculate_max_redeem,
    get_or_create_loyalty,
    increment_stamps,
    redeem_points,
    refund_points,
    use_free_drink,
)
from tests.conftest import get_loyalty, insert_loyalty, insert_points_history


# --- accrue_points ---


@pytest.mark.asyncio
async def test_accrue_points_500_rub(test_db):
    """Начисление 25 баллов за 500 рублей."""
    user_id = 1001
    order_id = 1

    points_earned = await accrue_points(user_id, 500, order_id)

    assert points_earned == 25
    loyalty_data = await get_loyalty(test_db, user_id)
    assert loyalty_data["points"] == 25


@pytest.mark.asyncio
async def test_accrue_points_99_rub_zero(test_db):
    """Начисление 0 баллов за 99 рублей (округление вниз)."""
    user_id = 1002
    order_id = 2

    points_earned = await accrue_points(user_id, 99, order_id)

    assert points_earned == 0
    loyalty_data = await get_loyalty(test_db, user_id)
    # Запись не должна создаваться при 0 баллах
    assert loyalty_data is None


@pytest.mark.asyncio
async def test_accrue_points_150_rub(test_db):
    """Начисление 5 баллов за 150 рублей (150 // 100 = 1)."""
    user_id = 1003
    order_id = 3

    points_earned = await accrue_points(user_id, 150, order_id)

    assert points_earned == 5
    loyalty_data = await get_loyalty(test_db, user_id)
    assert loyalty_data["points"] == 5


@pytest.mark.asyncio
async def test_accrue_points_updates_total_orders(test_db):
    """Проверка обновления total_orders при начислении."""
    user_id = 1004
    await insert_loyalty(test_db, user_id, points=100, total_orders=5, total_spent=5000)

    await accrue_points(user_id, 500, order_id=10)

    loyalty_data = await get_loyalty(test_db, user_id)
    assert loyalty_data["total_orders"] == 6


@pytest.mark.asyncio
async def test_accrue_points_updates_total_spent(test_db):
    """Проверка обновления total_spent при начислении."""
    user_id = 1005
    await insert_loyalty(test_db, user_id, points=100, total_orders=5, total_spent=5000)

    await accrue_points(user_id, 750, order_id=11)

    loyalty_data = await get_loyalty(test_db, user_id)
    assert loyalty_data["total_spent"] == 5750


@pytest.mark.asyncio
async def test_accrue_points_creates_history_record(test_db):
    """Проверка создания записи в points_history."""
    user_id = 1006
    order_id = 12

    await accrue_points(user_id, 500, order_id)

    async with aiosqlite.connect(test_db) as db:
        cursor = await db.execute(
            """SELECT amount, operation, order_id, description
               FROM points_history WHERE user_id = ?""",
            (user_id,)
        )
        row = await cursor.fetchone()

    assert row is not None
    assert row[0] == 25  # amount
    assert row[1] == "accrual"  # operation
    assert row[2] == order_id  # order_id
    assert str(order_id) in row[3]  # description содержит order_id


@pytest.mark.asyncio
async def test_accrue_points_accumulates(test_db):
    """Баллы накапливаются при нескольких заказах."""
    user_id = 1007

    await accrue_points(user_id, 500, order_id=20)  # +25
    await accrue_points(user_id, 300, order_id=21)  # +15

    loyalty_data = await get_loyalty(test_db, user_id)
    assert loyalty_data["points"] == 40
    assert loyalty_data["total_orders"] == 2


# --- redeem_points ---


@pytest.mark.asyncio
async def test_redeem_points_success(test_db):
    """Успешное списание баллов при достаточном балансе."""
    user_id = 2001
    await insert_loyalty(test_db, user_id, points=100)

    result = await redeem_points(user_id, 50, order_id=30)

    assert result is True
    loyalty_data = await get_loyalty(test_db, user_id)
    assert loyalty_data["points"] == 50


@pytest.mark.asyncio
async def test_redeem_points_insufficient_balance(test_db):
    """Отказ при недостаточном балансе баллов."""
    user_id = 2002
    await insert_loyalty(test_db, user_id, points=30)

    result = await redeem_points(user_id, 50, order_id=31)

    assert result is False
    loyalty_data = await get_loyalty(test_db, user_id)
    assert loyalty_data["points"] == 30  # баланс не изменился


@pytest.mark.asyncio
async def test_redeem_points_zero_amount(test_db):
    """Отказ при попытке списать 0 баллов."""
    user_id = 2003
    await insert_loyalty(test_db, user_id, points=100)

    result = await redeem_points(user_id, 0, order_id=32)

    assert result is False


@pytest.mark.asyncio
async def test_redeem_points_negative_amount(test_db):
    """Отказ при отрицательной сумме списания."""
    user_id = 2004
    await insert_loyalty(test_db, user_id, points=100)

    result = await redeem_points(user_id, -10, order_id=33)

    assert result is False


@pytest.mark.asyncio
async def test_redeem_points_creates_negative_history(test_db):
    """Проверка записи отрицательного amount в points_history."""
    user_id = 2005
    await insert_loyalty(test_db, user_id, points=100)

    await redeem_points(user_id, 30, order_id=34)

    async with aiosqlite.connect(test_db) as db:
        cursor = await db.execute(
            """SELECT amount, operation FROM points_history
               WHERE user_id = ? AND operation = 'redemption'""",
            (user_id,)
        )
        row = await cursor.fetchone()

    assert row is not None
    assert row[0] == -30  # отрицательный amount
    assert row[1] == "redemption"


@pytest.mark.asyncio
async def test_redeem_points_no_loyalty_record(test_db):
    """Отказ при отсутствии записи лояльности."""
    user_id = 2006  # нет записи в loyalty

    result = await redeem_points(user_id, 10, order_id=35)

    assert result is False


# --- refund_points ---


@pytest.mark.asyncio
async def test_refund_points_after_redemption(test_db):
    """Возврат баллов после отмены заказа с redemption."""
    user_id = 3001
    order_id = 40
    await insert_loyalty(test_db, user_id, points=70)  # было 100, списали 30
    await insert_points_history(
        test_db, user_id, amount=-30, operation="redemption", order_id=order_id
    )

    refunded = await refund_points(user_id, order_id)

    assert refunded == 30
    loyalty_data = await get_loyalty(test_db, user_id)
    assert loyalty_data["points"] == 100


@pytest.mark.asyncio
async def test_refund_points_no_redemption(test_db):
    """Возврат 0 при отсутствии redemption для заказа."""
    user_id = 3002
    order_id = 41
    await insert_loyalty(test_db, user_id, points=100)

    refunded = await refund_points(user_id, order_id)

    assert refunded == 0


@pytest.mark.asyncio
async def test_refund_points_creates_refund_history(test_db):
    """Проверка записи refund в points_history."""
    user_id = 3003
    order_id = 42
    await insert_loyalty(test_db, user_id, points=50)
    await insert_points_history(
        test_db, user_id, amount=-25, operation="redemption", order_id=order_id
    )

    await refund_points(user_id, order_id)

    async with aiosqlite.connect(test_db) as db:
        cursor = await db.execute(
            """SELECT amount, operation FROM points_history
               WHERE user_id = ? AND operation = 'refund'""",
            (user_id,)
        )
        row = await cursor.fetchone()

    assert row is not None
    assert row[0] == 25  # положительный amount
    assert row[1] == "refund"


@pytest.mark.asyncio
async def test_refund_points_different_order_not_affected(test_db):
    """Refund для другого order_id не влияет на текущий."""
    user_id = 3004
    await insert_loyalty(test_db, user_id, points=100)
    await insert_points_history(
        test_db, user_id, amount=-30, operation="redemption", order_id=50
    )

    refunded = await refund_points(user_id, order_id=99)  # другой order_id

    assert refunded == 0


# --- increment_stamps ---


@pytest.mark.asyncio
async def test_increment_stamps_from_zero(test_db):
    """Увеличение штампов с 0 до 1, бесплатный напиток не заработан."""
    user_id = 4001

    new_stamps, earned_free = await increment_stamps(user_id)

    assert new_stamps == 1
    assert earned_free is False


@pytest.mark.asyncio
async def test_increment_stamps_to_six(test_db):
    """Увеличение штампов с 5 до 6, заработан бесплатный напиток."""
    user_id = 4002
    await insert_loyalty(test_db, user_id, stamps=5)

    new_stamps, earned_free = await increment_stamps(user_id)

    assert new_stamps == 6
    assert earned_free is True


@pytest.mark.asyncio
async def test_increment_stamps_above_six(test_db):
    """Штампы выше 6 - earned_free_drink все еще True."""
    user_id = 4003
    await insert_loyalty(test_db, user_id, stamps=6)

    new_stamps, earned_free = await increment_stamps(user_id)

    assert new_stamps == 7
    assert earned_free is True


@pytest.mark.asyncio
async def test_increment_stamps_updates_db(test_db):
    """Проверка обновления stamps в БД."""
    user_id = 4004
    await insert_loyalty(test_db, user_id, stamps=3)

    await increment_stamps(user_id)

    loyalty_data = await get_loyalty(test_db, user_id)
    assert loyalty_data["stamps"] == 4


@pytest.mark.asyncio
async def test_increment_stamps_creates_loyalty_if_not_exists(test_db):
    """Создание записи лояльности если её нет."""
    user_id = 4005  # нет записи

    new_stamps, _ = await increment_stamps(user_id)

    assert new_stamps == 1
    loyalty_data = await get_loyalty(test_db, user_id)
    assert loyalty_data is not None
    assert loyalty_data["stamps"] == 1


# --- calculate_max_redeem ---


def test_calculate_max_redeem_limited_by_percent():
    """Лимит по проценту: 30% от 1000 = 300, баллов 500."""
    result = calculate_max_redeem(order_total=1000, user_points=500)
    assert result == 300


def test_calculate_max_redeem_limited_by_points():
    """Лимит по баллам: 30% от 1000 = 300, баллов 100."""
    result = calculate_max_redeem(order_total=1000, user_points=100)
    assert result == 100


def test_calculate_max_redeem_small_order():
    """Маленький заказ: 30% от 100 = 30, баллов 500."""
    result = calculate_max_redeem(order_total=100, user_points=500)
    assert result == 30


def test_calculate_max_redeem_zero_points():
    """Ноль баллов - списать нечего."""
    result = calculate_max_redeem(order_total=1000, user_points=0)
    assert result == 0


def test_calculate_max_redeem_zero_order():
    """Нулевой заказ - 30% от 0 = 0."""
    result = calculate_max_redeem(order_total=0, user_points=500)
    assert result == 0


def test_calculate_max_redeem_exact_match():
    """Точное совпадение: баллы равны 30% от заказа."""
    result = calculate_max_redeem(order_total=1000, user_points=300)
    assert result == 300


# --- use_free_drink ---


@pytest.mark.asyncio
async def test_use_free_drink_success(test_db):
    """Успешное использование бесплатного напитка при 6 штампах."""
    user_id = 5001
    await insert_loyalty(test_db, user_id, stamps=6)

    result = await use_free_drink(user_id)

    assert result is True
    loyalty_data = await get_loyalty(test_db, user_id)
    assert loyalty_data["stamps"] == 0


@pytest.mark.asyncio
async def test_use_free_drink_more_than_six(test_db):
    """Использование при 7+ штампах - сбрасывает в 0."""
    user_id = 5002
    await insert_loyalty(test_db, user_id, stamps=8)

    result = await use_free_drink(user_id)

    assert result is True
    loyalty_data = await get_loyalty(test_db, user_id)
    assert loyalty_data["stamps"] == 0


@pytest.mark.asyncio
async def test_use_free_drink_not_enough_stamps(test_db):
    """Отказ при недостаточном количестве штампов."""
    user_id = 5003
    await insert_loyalty(test_db, user_id, stamps=5)

    result = await use_free_drink(user_id)

    assert result is False
    loyalty_data = await get_loyalty(test_db, user_id)
    assert loyalty_data["stamps"] == 5  # не изменилось


@pytest.mark.asyncio
async def test_use_free_drink_no_loyalty_record(test_db):
    """Отказ при отсутствии записи лояльности."""
    user_id = 5004  # нет записи

    result = await use_free_drink(user_id)

    assert result is False


# --- get_or_create_loyalty ---


@pytest.mark.asyncio
async def test_get_or_create_loyalty_existing(test_db):
    """Получение существующей записи лояльности."""
    user_id = 6001
    await insert_loyalty(test_db, user_id, points=150, stamps=3, total_orders=10, total_spent=12000)

    result = await get_or_create_loyalty(user_id)

    assert result["points"] == 150
    assert result["stamps"] == 3
    assert result["total_orders"] == 10
    assert result["total_spent"] == 12000


@pytest.mark.asyncio
async def test_get_or_create_loyalty_new(test_db):
    """Создание новой записи лояльности."""
    user_id = 6002  # нет записи

    result = await get_or_create_loyalty(user_id)

    assert result["points"] == 0
    assert result["stamps"] == 0
    assert result["total_orders"] == 0
    assert result["total_spent"] == 0


@pytest.mark.asyncio
async def test_get_or_create_loyalty_persists(test_db):
    """Созданная запись сохраняется в БД."""
    user_id = 6003

    await get_or_create_loyalty(user_id)

    loyalty_data = await get_loyalty(test_db, user_id)
    assert loyalty_data is not None
    assert loyalty_data["points"] == 0


# --- Константы ---


def test_constants_values():
    """Проверка значений констант."""
    assert POINTS_PER_100_RUB == 5
    assert MAX_REDEEM_PERCENT == 30
    assert STAMPS_FOR_FREE_DRINK == 6
