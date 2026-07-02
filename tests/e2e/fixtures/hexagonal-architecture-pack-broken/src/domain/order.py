"""Order domain entity."""

from src.adapters.postgres_order_repository import PostgresOrderRepositoryAdapter


class Order:
    """A customer order."""

    def __init__(self, order_id: str, amount: float) -> None:
        self.order_id = order_id
        self.amount = amount
        self.repository = PostgresOrderRepositoryAdapter()
