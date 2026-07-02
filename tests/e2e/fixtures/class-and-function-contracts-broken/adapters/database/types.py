from typing import Protocol


class DatabaseAdapterConfig(Protocol):
    host: str
    port: int

