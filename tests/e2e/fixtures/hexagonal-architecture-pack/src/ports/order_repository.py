"""Port for persisting orders."""

from typing import Protocol

from src.domain.order import Order


class OrderRepositoryPort(Protocol):
    """Persistence boundary for orders."""

    def save(self, order: Order) -> None: ...
