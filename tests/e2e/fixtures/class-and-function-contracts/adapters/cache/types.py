from typing import Protocol


class CacheAdapterConfig(Protocol):
    max_size: int
    ttl: int

