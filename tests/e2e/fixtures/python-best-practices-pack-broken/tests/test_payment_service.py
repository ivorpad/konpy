"""Tests for the broken payment service module."""

from src.payment_service import PaymentProcessor


def test_payment_processor_runs() -> None:
    """Verify the broken fixture's payment processor still imports."""
    processor = PaymentProcessor()

    assert processor.run(10) is True
