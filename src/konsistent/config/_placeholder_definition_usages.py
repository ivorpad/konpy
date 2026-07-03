"""Placeholder-usage scanning for declaration/export/import definition lists.

Walks declareX/exportX/importX list entries (plus their extend/implement
fields) looking for ${name} placeholder usages.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel

from konsistent.config._placeholder_shared import _push_string_usages, _to_alias_dict, _Usage


def _collect_usages_recursively(
    *,
    value: object,
    key: str,
    declared: set[str],
    usages: list[_Usage],
) -> None:
    if isinstance(value, str):
        _push_string_usages(value=value, key=key, declared=declared, usages=usages)
        return

    if isinstance(value, BaseModel):
        _collect_usages_recursively(
            value=value.model_dump(by_alias=True, exclude_none=True),
            key=key,
            declared=declared,
            usages=usages,
        )
        return

    if isinstance(value, Mapping):
        for item in value.values():
            _collect_usages_recursively(
                value=item,
                key=key,
                declared=declared,
                usages=usages,
            )
        return

    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        for item in value:
            _collect_usages_recursively(
                value=item,
                key=key,
                declared=declared,
                usages=usages,
            )


def _collect_usages_in_definition_list(
    *,
    list_: Sequence[object] | None,
    key: str,
    object_fields: Sequence[str],
    declared: set[str],
    usages: list[_Usage],
    array_fields: Sequence[str] = (),
    extend_field: bool = False,
    implement_field: bool = False,
) -> None:
    if list_ is None:
        return

    for entry in list_:
        if isinstance(entry, str):
            _push_string_usages(value=entry, key=key, declared=declared, usages=usages)
            continue

        entry_data = _to_alias_dict(entry)
        for field in object_fields:
            value = entry_data.get(field)
            if isinstance(value, str):
                _push_string_usages(value=value, key=key, declared=declared, usages=usages)

        for field in array_fields:
            value = entry_data.get(field)
            if not isinstance(value, list):
                continue
            for item in value:
                if isinstance(item, str):
                    _push_string_usages(value=item, key=key, declared=declared, usages=usages)

        if extend_field:
            _collect_extend_usages(
                value=entry_data.get("extend"),
                key=key,
                declared=declared,
                usages=usages,
            )

        if implement_field and isinstance(entry_data.get("implement"), list):
            for item in entry_data["implement"]:
                _collect_extend_usages(value=item, key=key, declared=declared, usages=usages)


def _collect_extend_usages(
    *,
    value: object,
    key: str,
    declared: set[str],
    usages: list[_Usage],
) -> None:
    if isinstance(value, str):
        _push_string_usages(value=value, key=key, declared=declared, usages=usages)
        return

    if isinstance(value, BaseModel | Mapping):
        value_data = _to_alias_dict(value)
        type_value = value_data.get("type")
        if isinstance(type_value, str):
            _push_string_usages(value=type_value, key=key, declared=declared, usages=usages)


__all__: list[str] = []
