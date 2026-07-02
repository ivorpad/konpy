from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core import BaseAdapter, Connectable


class CacheAdapter(BaseAdapter, Connectable):
    async def get(self, key: str) -> str | None:
        return key

