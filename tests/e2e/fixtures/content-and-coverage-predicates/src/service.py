# SPDX-License-Identifier: Apache-2.0
"""Service module."""


class Service:
    """Example service."""

    def run(self, value: str) -> str:
        """Run the service."""
        return value


def create_service(config: str) -> Service:
    """Create a service."""
    _ = config
    return Service()
