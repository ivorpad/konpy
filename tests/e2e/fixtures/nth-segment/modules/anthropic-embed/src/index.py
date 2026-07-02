from typing import Final, TypeAlias

AnthropicEmbed: TypeAlias = dict[str, str]

embed: Final[AnthropicEmbed] = {"model": "claude-3"}

