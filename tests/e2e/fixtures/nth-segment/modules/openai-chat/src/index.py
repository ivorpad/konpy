from typing import Final, TypeAlias

OpenaiChat: TypeAlias = dict[str, str]

chat: Final[OpenaiChat] = {"model": "gpt-4"}

