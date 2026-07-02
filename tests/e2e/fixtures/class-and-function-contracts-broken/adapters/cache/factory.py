from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .adapter import CacheAdapter
    from .types import CacheAdapterConfig


def createCacheAdapter(config: CacheAdapterConfig) -> CacheAdapter:
    return config

