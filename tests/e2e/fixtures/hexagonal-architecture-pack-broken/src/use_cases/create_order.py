"""Use case for creating a new order."""

from src.domain.order import Order


def create_order(order_id: str, amount: float) -> Order:
    """Create a new order."""
    return Order(order_id=order_id, amount=amount)
