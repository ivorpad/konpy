"""Port for persisting orders."""

from src.domain.order import Order


class OrderRepository:
    """Persistence boundary for orders."""

    def save(self, order: Order) -> None: ...
