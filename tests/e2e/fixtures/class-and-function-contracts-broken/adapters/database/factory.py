from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .adapter import DatabaseAdapter
    from .types import DatabaseAdapterConfig


def createDatabaseAdapter(config: str) -> int:
    return 1

