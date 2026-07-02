from typing import Final, Protocol, TypeAlias


class BaseInterface(Protocol):
    pass


class BaseClass:
    pass


class Serializable(Protocol):
    pass


class LocalConfig(Protocol):
    pass


class LocalResult(Protocol):
    pass


LocalType: TypeAlias = str
localConstant: Final[str] = "value"


def createLocal(config: LocalConfig) -> LocalResult:
    return config


class LocalInterface(BaseInterface, Protocol):
    pass


class LocalClass(BaseClass, Serializable):
    pass

