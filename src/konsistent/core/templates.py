"""Template expression resolution for ``${name}`` / ``${name.method(arg)}``.
Port of core/template.ts: unknown placeholder names and unknown methods leave
the original token untouched.
"""

import re
from collections.abc import Mapping

from konsistent.core.placeholders import PlaceholderValue

TEMPLATE_PATTERN = r"\$\{(\w+)(?:\.(\w+)\(([^}]*)\))?\}"

_TEMPLATE_REGEX = re.compile(TEMPLATE_PATTERN)


def _to_index(arg: str) -> int:
    # JS Number() semantics: "" -> 0, whitespace trimmed, non-numeric or
    # fractional values never address a segment.
    stripped = arg.strip()
    if not stripped:
        return 0
    try:
        number = float(stripped)
    except ValueError:
        return -1
    if not number.is_integer():
        return -1
    return int(number)


def resolve_template(template: str, placeholders: Mapping[str, PlaceholderValue]) -> str:
    """Substitute ``${name}`` / ``${name.method(arg)}`` tokens with placeholder values."""

    def replace(match: re.Match[str]) -> str:
        original = match.group(0)
        name, method, arg = match.group(1), match.group(2), match.group(3)

        placeholder = placeholders.get(name)
        if placeholder is None:
            return original

        if method is None:
            return placeholder.to_string()

        match method:
            case "toString":
                return placeholder.to_string()
            case "toPascalCase":
                return placeholder.to_pascal_case()
            case "toCamelCase":
                return placeholder.to_camel_case()
            case "toKebabCase":
                return placeholder.to_kebab_case()
            case "toSnakeCase":
                return placeholder.to_snake_case()
            case "toConstantCase":
                return placeholder.to_constant_case()
            case "toFlatCase":
                return placeholder.to_flat_case()
            case "toNthSegment":
                return placeholder.to_nth_segment(_to_index(arg))
            case "toNthSegmentPascalCase":
                return placeholder.to_nth_segment_pascal_case(_to_index(arg))
            case "toNthSegmentCamelCase":
                return placeholder.to_nth_segment_camel_case(_to_index(arg))
            case "extract":
                return placeholder.extract(arg)
            case _:
                return original

    return _TEMPLATE_REGEX.sub(replace, template)
