from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from konsistent.config.schema import MustBlockV1, MustPredicatesV1
from konsistent.predicates.registry import iter_predicate_items

_TEMPLATE_RE = re.compile(r"\$\{[^}]*\}")
_CAMEL_RE = re.compile(r"([a-z0-9])([A-Z])")


def _strip_template_expressions(value: str) -> str:
    return _TEMPLATE_RE.sub("", value)


def _camel_to_kebab(value: str) -> str:
    return _CAMEL_RE.sub(r"\1-\2", value).lower()


def _derive_kebab_from_name(name: str) -> str:
    stripped = _strip_template_expressions(name)
    kebab = _camel_to_kebab(stripped)
    return re.sub(r"-{2,}", "-", kebab).strip("-")


def _file_to_kebab(file: str) -> str:
    return file.replace(".", "-").replace("/", "-").strip("-")


def _source_to_kebab(source: str) -> str:
    stripped = _strip_template_expressions(source)
    value = _CAMEL_RE.sub(r"\1-\2", stripped)
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).lower()
    return re.sub(r"-{2,}", "-", value).strip("-")


def _predicate_key_to_kebab(key: str) -> str:
    value = _CAMEL_RE.sub(r"\1-\2", key)
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).lower()
    return re.sub(r"-{2,}", "-", value).strip("-")


def _get(obj: Any, key: str) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key)
    return getattr(obj, key, None)


def _get_item_name(item: Any) -> str:
    if isinstance(item, str):
        return item
    return str(_get(item, "name") or "")


def _items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def _prefixed(prefix: str, kebab: str, suffix: str = "") -> str:
    if kebab:
        return f"{prefix}-{kebab}{suffix}"
    return f"{prefix}{suffix}"


def _boolean_import_name(*, positive: str, negative: str, item: Any, negated: bool) -> str:
    return positive if (item is False) == negated else negative


def _rule(key: str, items: list[Any], *, negated: bool) -> str:
    first = items[0]
    match key:
        case "haveType":
            return f"must-not-be-{first}" if negated else f"must-be-{first}"
        case "haveFiles":
            return _prefixed(
                "must-not-have" if negated else "must-have",
                _file_to_kebab(_strip_template_expressions(str(first))),
            )
        case "matchContent":
            return "must-not-match-content" if negated else "must-match-content"
        case "havePairedFile":
            return _prefixed(
                "must-not-have-paired" if negated else "must-have-paired",
                _source_to_kebab(str(first)),
            )
        case "declareTypes":
            return _prefixed(
                "must-not-declare" if negated else "must-declare",
                _derive_kebab_from_name(_get_item_name(first)),
                "-type",
            )
        case "declareConstants":
            return _prefixed(
                "must-not-declare" if negated else "must-declare",
                _derive_kebab_from_name(_get_item_name(first)),
                "-constant",
            )
        case "declareFunctions":
            return _prefixed(
                "must-not-declare" if negated else "must-declare",
                _derive_kebab_from_name(_get_item_name(first)),
                "-function",
            )
        case "declareClasses":
            return _prefixed(
                "must-not-declare" if negated else "must-declare",
                _derive_kebab_from_name(_get_item_name(first)),
                "-class",
            )
        case "declareInterfaces":
            return _prefixed(
                "must-not-declare" if negated else "must-declare",
                _derive_kebab_from_name(_get_item_name(first)),
                "-interface",
            )
        case "export":
            return _prefixed(
                "must-not-export" if negated else "must-export",
                _derive_kebab_from_name(_get_item_name(first)),
            )
        case "exportTypes":
            return _prefixed(
                "must-not-export" if negated else "must-export",
                _derive_kebab_from_name(_get_item_name(first)),
                "-type",
            )
        case "exportConstants":
            return _prefixed(
                "must-not-export" if negated else "must-export",
                _derive_kebab_from_name(_get_item_name(first)),
                "-constant",
            )
        case "exportFunctions":
            return _prefixed(
                "must-not-export" if negated else "must-export",
                _derive_kebab_from_name(_get_item_name(first)),
                "-function",
            )
        case "exportClasses":
            return _prefixed(
                "must-not-export" if negated else "must-export",
                _derive_kebab_from_name(_get_item_name(first)),
                "-class",
            )
        case "exportInterfaces":
            return _prefixed(
                "must-not-export" if negated else "must-export",
                _derive_kebab_from_name(_get_item_name(first)),
                "-interface",
            )
        case "import":
            return _prefixed(
                "must-not-import" if negated else "must-import",
                _derive_kebab_from_name(_get_item_name(first)),
            )
        case "importFrom":
            return _prefixed(
                "must-not-import-from" if negated else "must-import-from",
                _source_to_kebab(str(first)),
            )
        case "importTypes":
            return _prefixed(
                "must-not-import" if negated else "must-import",
                _derive_kebab_from_name(_get_item_name(first)),
                "-type",
            )
        case "importFromCurrentDir":
            return _boolean_import_name(
                positive="must-import-from-current-dir",
                negative="must-not-import-from-current-dir",
                item=first,
                negated=negated,
            )
        case "importFromParents":
            return _boolean_import_name(
                positive="must-import-from-parents",
                negative="must-not-import-from-parents",
                item=first,
                negated=negated,
            )
        case "importFromExternals":
            return _boolean_import_name(
                positive="must-import-from-externals",
                negative="must-not-import-from-externals",
                item=first,
                negated=negated,
            )
        case "importTypesFromCurrentDir":
            return _boolean_import_name(
                positive="must-import-type-from-current-dir",
                negative="must-not-import-type-from-current-dir",
                item=first,
                negated=negated,
            )
        case "importTypesFromParents":
            return _boolean_import_name(
                positive="must-import-type-from-parents",
                negative="must-not-import-type-from-parents",
                item=first,
                negated=negated,
            )
        case "importTypesFromExternals":
            return _boolean_import_name(
                positive="must-import-type-from-externals",
                negative="must-not-import-type-from-externals",
                item=first,
                negated=negated,
            )
        case "useDeclarationOrder":
            return _prefixed(
                "must-not-use" if negated else "must-use",
                _derive_kebab_from_name(str(first)),
                "-declaration-order",
            )
        case "haveDocstrings":
            return "must-not-have-docstrings" if negated else "must-have-docstrings"
        case "annotateFunctions":
            return "must-not-annotate-functions" if negated else "must-annotate-functions"
        case _:
            return _prefixed(
                "must-not" if negated else "must",
                _predicate_key_to_kebab(key),
            )


def _predicate_items(selected: MustPredicatesV1) -> list[tuple[str, Any]]:
    return iter_predicate_items(selected)


def generate_convention_name(
    *,
    must: MustPredicatesV1 | list[MustBlockV1] | None = None,
    must_not: MustPredicatesV1 | None = None,
    predicate_registry: Any | None = None,
) -> str:
    del predicate_registry

    selected: MustPredicatesV1 | None = None
    negated = False

    if isinstance(must, list):
        first_block = must[0] if must else None
        if first_block is not None and first_block.must is not None:
            selected = first_block.must
        elif first_block is not None and first_block.mustNot is not None:
            selected = first_block.mustNot
            negated = True
    elif must is not None:
        selected = must

    if selected is None and must_not is not None:
        selected = must_not
        negated = True

    if selected is None:
        return "convention"

    predicate_items = _predicate_items(selected)
    if not predicate_items:
        return "convention"

    first_key, first_value = predicate_items[0]
    items = _items(first_value)
    name = _rule(first_key, items, negated=negated)
    if name == "convention":
        return name

    if len(predicate_items) > 1 or (isinstance(first_value, list) and len(first_value) > 1):
        return f"{name}-and-more"
    return name


__all__ = ["generate_convention_name"]
