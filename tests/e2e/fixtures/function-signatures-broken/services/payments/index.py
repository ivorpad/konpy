from typing import Any, Protocol


class PaymentsConfig(Protocol):
    api_key: str


class PaymentsService(Protocol):
    def charge(self) -> None: ...


class PaymentsLogger(Protocol):
    def info(self, message: str) -> None: ...


def createPaymentsService(
    config: PaymentsConfig,
    logger: PaymentsLogger,
) -> Any:
    logger.info(config.api_key)
    return {"charge": lambda: None}

