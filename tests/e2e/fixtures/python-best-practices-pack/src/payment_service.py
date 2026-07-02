"""Payment service module."""


class PaymentService:
    """Service responsible for payment operations."""

    def charge(self, amount: int) -> bool:
        """Charge the requested amount."""
        return amount > 0
