from src.service import create_service


def test_create_service() -> None:
    assert create_service("config").run("ok") == "ok"
