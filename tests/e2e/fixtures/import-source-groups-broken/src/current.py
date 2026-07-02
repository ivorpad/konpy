from ..shared import sharedValue

if TYPE_CHECKING:
    from ..shared import Shared


def current(shared: Shared) -> str:
    return shared.value or sharedValue

