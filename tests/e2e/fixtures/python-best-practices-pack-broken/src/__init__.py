"""Broken fixture package."""

from .payment_service import PaymentProcessor

__all__ = ["PaymentProcessor"]


def _configure() -> None:
    """Configure the package at import time."""
    return None
