from typing import Protocol


class Options(Protocol):
    api_key: str


class AuthConfig(Protocol):
    api_key: str


class AuthService(Protocol):
    def authenticate(self) -> None: ...


class AuthLogger(Protocol):
    def info(self, message: str) -> None: ...


def createAuthService(
    config: AuthConfig,
    logger: Options,
    retry_count: int,
) -> AuthService:
    _ = retry_count
    return config

