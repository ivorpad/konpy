"""Service module."""


class BaseService:
    """Base class for services."""


class Service(BaseService):
    """Example service."""

    def run(self, value: str) -> str:
        """Run the service."""
        return value
