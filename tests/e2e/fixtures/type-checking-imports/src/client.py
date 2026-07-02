from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ..shared import SharedConfig
    from .local_types import LocalModel


def build_client(
    model: LocalModel,
    config: SharedConfig,
    metadata: Mapping[str, str],
) -> dict[str, str]:
    return {"id": model.id, "name": config.name, **metadata}

