from datetime import datetime
from enum import Enum
from pydantic import BaseModel


class OrderStatus(str, Enum):
    PENDING = "pending"         # ожидает подтверждения
    CONFIRMED = "confirmed"     # подтверждён, в очереди
    PREPARING = "preparing"     # готовится
    READY = "ready"             # готов к выдаче
    COMPLETED = "completed"     # выдан
    CANCELLED = "cancelled"     # отменён

    @property
    def display_name(self) -> str:
        names = {
            "pending": "Ожидает",
            "confirmed": "Подтверждён",
            "preparing": "Готовится",
            "ready": "Готов",
            "completed": "Выдан",
            "cancelled": "Отменён",
        }
        return names[self.value]


class MenuItem(BaseModel):
    id: int
    name: str
    price: int  # в рублях
    available: bool = True


class OrderItem(BaseModel):
    menu_item_id: int
    name: str
    price: int
    quantity: int = 1


class Order(BaseModel):
    id: int
    user_id: int
    user_name: str
    items: list[OrderItem]
    total: int
    pickup_time: str  # "через 15 мин", "через 30 мин" и т.д.
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime


class CartItem(BaseModel):
    """Элемент корзины (до оформления заказа)"""
    menu_item_id: int
    name: str
    price: int
    quantity: int = 1
