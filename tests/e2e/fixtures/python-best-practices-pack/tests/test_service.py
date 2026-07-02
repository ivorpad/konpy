"""Tests for the general service module."""

from src.service import create_service


def test_create_service_returns_service() -> None:
    """Verify the service factory returns a working service."""
    service = create_service("primary")

    assert service.run("ok") == "ok"
