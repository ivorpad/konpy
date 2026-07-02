from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core import BaseAdapter, Connectable


class DatabaseAdapter(BaseAdapter, Connectable):
    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

