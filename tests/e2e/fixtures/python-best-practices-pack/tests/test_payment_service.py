"""Tests for the payment service module."""

from src.payment_service import PaymentService


def test_payment_service_charges_positive_amounts() -> None:
    """Verify positive charges are accepted."""
    service = PaymentService()

    assert service.charge(10) is True
