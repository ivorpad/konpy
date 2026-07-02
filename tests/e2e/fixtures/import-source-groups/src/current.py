from .helper import helper

if TYPE_CHECKING:
    from .helper import HelperOptions


def current(options: HelperOptions) -> str:
    return f"{helper}:{options.value}"

