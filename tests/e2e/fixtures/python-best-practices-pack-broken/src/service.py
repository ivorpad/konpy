from .payment_service import PaymentProcessor

__all__ = ["_private_helper"]


def _private_helper(value):
    return PaymentProcessor().run(value)
