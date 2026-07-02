from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core import BaseAdapter


class DatabaseAdapter(WrongBase):
    async def connect(self) -> None:
        return None

