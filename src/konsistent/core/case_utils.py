"""Case conversion utilities. Port of core/case-utils.ts plus the case-map
derivation helpers from core/runner.ts (invertMap, deriveCamelToPascalMap)."""

import re

_CAMEL_BOUNDARY = re.compile(r"([a-z])([A-Z])")
_SEPARATORS = re.compile(r"[-_]")


def split_words(value: str) -> list[str]:
    return [word for word in _SEPARATORS.split(_CAMEL_BOUNDARY.sub(r"\1-\2", value)) if word]


def _title(word: str) -> str:
    return word[:1].upper() + word[1:].lower()


def to_pascal_case(value: str) -> str:
    return "".join(_title(word) for word in split_words(value))


def to_camel_case(value: str) -> str:
    words = split_words(value)
    if not words:
        return ""
    return words[0].lower() + "".join(_title(word) for word in words[1:])


def to_kebab_case(value: str) -> str:
    return "-".join(word.lower() for word in split_words(value))


def to_snake_case(value: str) -> str:
    return "_".join(word.lower() for word in split_words(value))


def to_constant_case(value: str) -> str:
    return "_".join(word.upper() for word in split_words(value))


def invert_map(mapping: dict[str, str] | None) -> dict[str, str] | None:
    if mapping is None:
        return None
    return {value: key for key, value in mapping.items()}


def derive_camel_to_pascal_map(
    kebab_to_pascal_map: dict[str, str] | None = None,
    kebab_to_camel_map: dict[str, str] | None = None,
) -> dict[str, str] | None:
    if kebab_to_pascal_map is None and kebab_to_camel_map is None:
        return None

    all_kebab_keys = set(kebab_to_pascal_map or {}) | set(kebab_to_camel_map or {})

    result: dict[str, str] = {}
    for kebab_key in all_kebab_keys:
        camel_value = (kebab_to_camel_map or {}).get(kebab_key) or to_camel_case(kebab_key)
        pascal_value = (kebab_to_pascal_map or {}).get(kebab_key) or to_pascal_case(kebab_key)
        result[camel_value] = pascal_value
    return result
