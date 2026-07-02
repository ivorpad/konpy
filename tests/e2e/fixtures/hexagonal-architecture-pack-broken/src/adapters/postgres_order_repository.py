"""Postgres adapter implementing the order repository port."""

from src.domain.order import Order
from src.ports.order_repository import OrderRepository


class PostgresOrderRepository(OrderRepository):
    """Persists orders in Postgres."""

    def save(self, order: Order) -> None:
        raise NotImplementedError
