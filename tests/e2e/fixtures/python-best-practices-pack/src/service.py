"""General service module."""


class Service:
    """Service used by the clean fixture."""

    def run(self, value: str) -> str:
        """Return the provided value."""
        return value


def create_service(name: str) -> Service:
    """Create a configured service."""
    _ = name
    return Service()
