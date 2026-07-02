from typing import Protocol


class AuthConfig(Protocol):
    api_key: str


class AuthService(Protocol):
    def authenticate(self) -> None: ...


class AuthLogger(Protocol):
    def info(self, message: str) -> None: ...


def createAuthService(
    config: AuthConfig,
    logger: AuthLogger,
    retry_count: int,
) -> AuthService:
    logger.info(f"auth retries: {retry_count}")
    return config

