from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel

from konpy.config.schema import ConfigV1


def collect_deprecation_warnings(*, config: ConfigV1) -> list[str]:
    """Collect warnings for deprecated field names still in use across a config's conventions."""
    warnings: list[str] = []

    for index, convention in enumerate(config.conventions):
        prefix = f"conventions[{index}]"
        must = _get(convention, "must")

        if isinstance(must, list):
            for block_index, block in enumerate(must):
                _collect_block_warnings(
                    block=block,
                    path=f"{prefix}.must[{block_index}]",
                    warnings=warnings,
                )
        else:
            _collect_predicate_warnings(
                predicates=must,
                path=f"{prefix}.must",
                warnings=warnings,
            )

        _collect_predicate_warnings(
            predicates=_get(convention, "mustNot"),
            path=f"{prefix}.mustNot",
            warnings=warnings,
        )

    return warnings


def _collect_block_warnings(*, block: object, path: str, warnings: list[str]) -> None:
    _collect_predicate_warnings(
        predicates=_get(block, "must"),
        path=f"{path}.must",
        warnings=warnings,
    )
    _collect_predicate_warnings(
        predicates=_get(block, "mustNot"),
        path=f"{path}.mustNot",
        warnings=warnings,
    )


def _collect_predicate_warnings(*, predicates: object, path: str, warnings: list[str]) -> None:
    if predicates is None:
        return

    _collect_function_warnings(
        list_=_get(predicates, "declareFunctions"),
        path=f"{path}.declareFunctions",
        warnings=warnings,
    )
    _collect_function_warnings(
        list_=_get(predicates, "exportFunctions"),
        path=f"{path}.exportFunctions",
        warnings=warnings,
    )


def _collect_function_warnings(
    *,
    list_: list[object] | None,
    path: str,
    warnings: list[str],
) -> None:
    if list_ is None:
        return

    for index, entry in enumerate(list_):
        if _has_receive_param_of_type(entry):
            warnings.append(
                f'Warning: "receiveParamOfType" is deprecated in '
                f'{path}[{index}].receiveParamOfType. Use "receiveParamsOfTypes" instead.'
            )


def _has_receive_param_of_type(entry: object) -> bool:
    if isinstance(entry, str):
        return False
    if isinstance(entry, BaseModel):
        return "receiveParamOfType" in entry.model_fields_set
    if isinstance(entry, Mapping):
        return "receiveParamOfType" in entry
    return False


def _get(value: object, field: str) -> object:
    if isinstance(value, BaseModel):
        return getattr(value, field, None)
    if isinstance(value, Mapping):
        return value.get(field)
    return None


__all__ = ["collect_deprecation_warnings"]
