from typing import Protocol


class PaymentsConfig[T](Protocol):
    api_key: str
    client: T


class PaymentsService[T](Protocol):
    client: T

    def charge(self) -> None: ...


class PaymentsLogger(Protocol):
    def info(self, message: str) -> None: ...


def createPaymentsService(
    config: PaymentsConfig[str],
    logger: PaymentsLogger,
    timeout_ms: int,
) -> PaymentsService[str]:
    logger.info(f"payments timeout: {timeout_ms}")
    return config

