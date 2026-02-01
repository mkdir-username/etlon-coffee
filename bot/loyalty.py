"""Модуль программы лояльности."""
import logging
from datetime import datetime

import aiosqlite

from bot.database import DB_PATH

logger = logging.getLogger(__name__)

# Константы
POINTS_PER_100_RUB = 5        # 5 баллов за каждые 100 рублей
MAX_REDEEM_PERCENT = 30       # Максимум 30% заказа можно оплатить баллами
STAMPS_FOR_FREE_DRINK = 6     # 6 штампов = бесплатный напиток


async def get_or_create_loyalty(user_id: int) -> dict:
    """
    Получить или создать запись лояльности.
    Returns:
        {'points': int, 'stamps': int, 'total_orders': int, 'total_spent': int}
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT points, stamps, total_orders, total_spent FROM loyalty WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()

        if row:
            return {
                "points": row[0],
                "stamps": row[1],
                "total_orders": row[2],
                "total_spent": row[3],
            }

        await db.execute(
            "INSERT INTO loyalty (user_id) VALUES (?)",
            (user_id,)
        )
        await db.commit()

        logger.debug("loyalty_created", extra={"user_id": user_id})

        return {
            "points": 0,
            "stamps": 0,
            "total_orders": 0,
            "total_spent": 0,
        }


async def accrue_points(user_id: int, order_total: int, order_id: int) -> int:
    """
    Начислить баллы за заказ.
    Формула: order_total // 100 * POINTS_PER_100_RUB
    Returns: количество начисленных баллов
    """
    points_earned = (order_total // 100) * POINTS_PER_100_RUB

    if points_earned <= 0:
        return 0

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")

        try:
            await db.execute(
                "INSERT OR IGNORE INTO loyalty (user_id) VALUES (?)",
                (user_id,)
            )

            await db.execute(
                """UPDATE loyalty SET
                    points = points + ?,
                    total_orders = total_orders + 1,
                    total_spent = total_spent + ?,
                    updated_at = ?
                WHERE user_id = ?""",
                (points_earned, order_total, datetime.now(), user_id)
            )

            await db.execute(
                """INSERT INTO points_history
                   (user_id, amount, operation, order_id, description)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, points_earned, "accrual", order_id, f"Начисление за заказ #{order_id}")
            )

            await db.commit()

            logger.debug(
                "points_accrued",
                extra={"user_id": user_id, "points": points_earned, "order_id": order_id}
            )

            return points_earned

        except Exception as e:
            await db.rollback()
            logger.error(
                "accrue_points_failed",
                extra={"user_id": user_id, "order_id": order_id, "error": str(e)},
                exc_info=True
            )
            raise


async def increment_stamps(user_id: int) -> tuple[int, bool]:
    """
    Добавить штамп за заказ.
    Returns: (текущее количество штампов, получен ли бесплатный напиток)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")

        try:
            await db.execute(
                "INSERT OR IGNORE INTO loyalty (user_id) VALUES (?)",
                (user_id,)
            )

            cursor = await db.execute(
                "SELECT stamps FROM loyalty WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            current_stamps = row[0] if row else 0

            new_stamps = current_stamps + 1
            earned_free_drink = new_stamps >= STAMPS_FOR_FREE_DRINK

            # Не сбрасываем автоматически, только через use_free_drink
            await db.execute(
                "UPDATE loyalty SET stamps = ?, updated_at = ? WHERE user_id = ?",
                (new_stamps, datetime.now(), user_id)
            )

            await db.commit()

            logger.debug(
                "stamps_updated",
                extra={
                    "user_id": user_id,
                    "new_stamps": new_stamps,
                    "earned_free_drink": earned_free_drink
                }
            )

            return new_stamps, earned_free_drink

        except Exception as e:
            await db.rollback()
            logger.error(
                "increment_stamps_failed",
                extra={"user_id": user_id, "error": str(e)},
                exc_info=True
            )
            raise


async def redeem_points(user_id: int, amount: int, order_id: int) -> bool:
    """
    Списать баллы при оплате.
    Проверяет достаточность баллов.
    Returns: успех операции
    """
    if amount <= 0:
        return False

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")

        try:
            cursor = await db.execute(
                "SELECT points FROM loyalty WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()

            if not row or row[0] < amount:
                await db.rollback()
                logger.warning(
                    "redeem_insufficient_points",
                    extra={"user_id": user_id, "requested": amount, "available": row[0] if row else 0}
                )
                return False

            await db.execute(
                "UPDATE loyalty SET points = points - ?, updated_at = ? WHERE user_id = ?",
                (amount, datetime.now(), user_id)
            )

            await db.execute(
                """INSERT INTO points_history
                   (user_id, amount, operation, order_id, description)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, -amount, "redemption", order_id, f"Списание за заказ #{order_id}")
            )

            await db.commit()

            logger.debug(
                "points_redeemed",
                extra={"user_id": user_id, "amount": amount, "order_id": order_id}
            )

            return True

        except Exception as e:
            await db.rollback()
            logger.error(
                "redeem_points_failed",
                extra={"user_id": user_id, "order_id": order_id, "error": str(e)},
                exc_info=True
            )
            raise


async def refund_points(user_id: int, order_id: int) -> int:
    """
    Вернуть баллы при отмене заказа.
    Находит списанные баллы по order_id в истории и возвращает их.
    Returns: количество возвращённых баллов (0 если не было списаний)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # Ищем списание по этому заказу
        cursor = await db.execute(
            """SELECT amount FROM points_history
               WHERE user_id = ? AND order_id = ? AND operation = 'redemption'""",
            (user_id, order_id)
        )
        row = await cursor.fetchone()

        if not row:
            return 0

        # amount в redemption отрицательный, берём модуль
        redeemed_amount = abs(row[0])

        if redeemed_amount <= 0:
            return 0

        await db.execute("BEGIN IMMEDIATE")

        try:
            await db.execute(
                "UPDATE loyalty SET points = points + ?, updated_at = ? WHERE user_id = ?",
                (redeemed_amount, datetime.now(), user_id)
            )

            await db.execute(
                """INSERT INTO points_history
                   (user_id, amount, operation, order_id, description)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, redeemed_amount, "refund", order_id, f"Возврат за отмену заказа #{order_id}")
            )

            await db.commit()

            logger.debug(
                "points_refunded",
                extra={"user_id": user_id, "amount": redeemed_amount, "order_id": order_id}
            )

            return redeemed_amount

        except Exception as e:
            await db.rollback()
            logger.error(
                "refund_points_failed",
                extra={"user_id": user_id, "order_id": order_id, "error": str(e)},
                exc_info=True
            )
            raise


async def get_points_history(user_id: int, limit: int = 10) -> list[dict]:
    """Получить историю операций с баллами."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """SELECT amount, operation, order_id, description, created_at
               FROM points_history
               WHERE user_id = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (user_id, limit)
        )
        rows = await cursor.fetchall()

        return [
            {
                "amount": row[0],
                "operation": row[1],
                "order_id": row[2],
                "description": row[3],
                "created_at": row[4],
            }
            for row in rows
        ]


def calculate_max_redeem(order_total: int, user_points: int) -> int:
    """
    Рассчитать максимум баллов для списания.
    min(user_points, order_total * MAX_REDEEM_PERCENT / 100)
    """
    max_by_percent = (order_total * MAX_REDEEM_PERCENT) // 100
    return min(user_points, max_by_percent)


async def use_free_drink(user_id: int) -> bool:
    """
    Использовать бесплатный напиток (сбросить штампы).
    Returns: успех (были ли 6+ штампов)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")

        try:
            cursor = await db.execute(
                "SELECT stamps FROM loyalty WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()

            if not row or row[0] < STAMPS_FOR_FREE_DRINK:
                await db.rollback()
                logger.warning(
                    "use_free_drink_insufficient_stamps",
                    extra={"user_id": user_id, "stamps": row[0] if row else 0}
                )
                return False

            await db.execute(
                "UPDATE loyalty SET stamps = 0, updated_at = ? WHERE user_id = ?",
                (datetime.now(), user_id)
            )

            await db.commit()

            logger.debug(
                "free_drink_used",
                extra={"user_id": user_id, "stamps_before": row[0]}
            )

            return True

        except Exception as e:
            await db.rollback()
            logger.error(
                "use_free_drink_failed",
                extra={"user_id": user_id, "error": str(e)},
                exc_info=True
            )
            raise
