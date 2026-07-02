from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from konsistent.config.errors import Err, Ok
from konsistent.config.reference_expander import deep_merge, expand_references
from konsistent.config.schema import ReusableConventionV1
from konsistent.config.source_resolver import SourceMap


def build_source_map(entries: dict[str, list[dict[str, Any]]]) -> SourceMap:
    source_map: SourceMap = {}
    for prefix, conventions in entries.items():
        source_map[prefix] = {}
        for convention in conventions:
            parsed = ReusableConventionV1.model_validate(convention)
            source_map[prefix][parsed.name] = parsed
    return source_map


def dump(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(by_alias=True, exclude_none=True)
    if isinstance(value, list):
        return [dump(item) for item in value]
    if isinstance(value, dict):
        return {key: dump(item) for key, item in value.items()}
    return value


def ok_value(result: object) -> Any:
    assert isinstance(result, Ok)
    return result.value


def err_error(result: object) -> str:
    assert isinstance(result, Err)
    return result.error


class TestExpandReferences:
    def test_expands_string_ref_to_matching_reusable_convention(self) -> None:
        source_map = build_source_map(
            {
                "common": [
                    {
                        "name": "package-must-have-readme",
                        "description": "Every package must have a README.md.",
                        "paths": ["packages/{packageName}"],
                        "must": {"haveFiles": ["README.md"]},
                    }
                ]
            }
        )

        result = expand_references(
            conventions=["common/package-must-have-readme"],
            source_map=source_map,
        )

        expanded = ok_value(result)
        assert len(expanded.conventions) == 1
        assert dump(expanded.conventions[0]) == {
            "name": "package-must-have-readme",
            "description": "Every package must have a README.md.",
            "paths": ["packages/{packageName}"],
            "must": {"haveFiles": ["README.md"]},
        }
        assert expanded.identifiers == ["common/package-must-have-readme"]

    def test_expands_string_ref_with_must_not_predicates(self) -> None:
        source_map = build_source_map(
            {
                "common": [
                    {
                        "name": "no-debug",
                        "description": "Do not export debug helpers.",
                        "paths": ["packages/{packageName}"],
                        "mustNot": {"exportConstants": ["debug"]},
                    }
                ]
            }
        )

        result = expand_references(conventions=["common/no-debug"], source_map=source_map)

        expanded = ok_value(result)
        assert dump(expanded.conventions[0])["mustNot"] == {"exportConstants": ["debug"]}

    def test_emits_unknown_vendor_error_verbatim(self) -> None:
        result = expand_references(conventions=["missing/foo"], source_map={})

        assert err_error(result) == (
            'Unknown convention source "missing" referenced in conventions[0]. '
            "Declare it in conventionSources or fix the typo."
        )

    def test_emits_unknown_convention_error_with_available_list(self) -> None:
        source_map = build_source_map(
            {
                "common": [
                    {
                        "name": "available-one",
                        "description": "x",
                        "paths": "src/*.ts",
                        "must": {"haveType": "file"},
                    },
                    {
                        "name": "available-two",
                        "description": "x",
                        "paths": "src/*.ts",
                        "must": {"haveType": "file"},
                    },
                ]
            }
        )

        result = expand_references(conventions=["common/missing"], source_map=source_map)

        assert err_error(result) == (
            'No convention "missing" in source "common". The package exports: '
            "available-one, available-two."
        )

    def test_emits_paths_less_string_ref_error_verbatim(self) -> None:
        source_map = build_source_map(
            {
                "common": [
                    {
                        "name": "no-paths",
                        "description": "x",
                        "must": {"haveType": "file"},
                    }
                ]
            }
        )

        result = expand_references(conventions=["common/no-paths"], source_map=source_map)

        assert err_error(result) == (
            'Convention "common/no-paths" cannot be referenced by string; it has no '
            '"paths". Use { use: "common/no-paths", paths: [...] } form.'
        )

    def test_passes_hand_written_entries_through_as_expanded_conventions(self) -> None:
        hand_written = {
            "name": "manual",
            "paths": "src/*.ts",
            "must": {"haveType": "file"},
        }

        result = expand_references(conventions=[hand_written], source_map={})

        expanded = ok_value(result)
        assert dump(expanded.conventions[0]) == hand_written
        assert expanded.identifiers == ["manual"]

    def test_preserves_order_in_mixed_array_of_refs_and_hand_written_entries(self) -> None:
        source_map = build_source_map(
            {
                "common": [
                    {
                        "name": "first",
                        "description": "x",
                        "paths": "src/*.ts",
                        "must": {"haveType": "file"},
                    },
                    {
                        "name": "third",
                        "description": "x",
                        "paths": "src/*.ts",
                        "must": {"haveType": "directory"},
                    },
                ]
            }
        )
        hand_written = {
            "name": "second",
            "paths": "lib/*.ts",
            "must": {"haveType": "file"},
        }

        result = expand_references(
            conventions=["common/first", hand_written, "common/third"],
            source_map=source_map,
        )

        expanded = ok_value(result)
        assert [convention.name for convention in expanded.conventions] == [
            "first",
            "second",
            "third",
        ]

    def test_includes_conventions_index_in_unknown_vendor_error(self) -> None:
        result = expand_references(
            conventions=[{"paths": "src/*.ts", "must": {"haveType": "file"}}, "missing/foo"],
            source_map={},
        )

        assert "conventions[1]" in err_error(result)

    def test_expands_object_ref_and_merges_paths_supplied_at_use_site(self) -> None:
        source_map = build_source_map(
            {
                "common": [
                    {
                        "name": "no-paths",
                        "description": "x",
                        "must": {"haveFiles": ["README.md"]},
                    }
                ]
            }
        )

        result = expand_references(
            conventions=[
                {
                    "use": "common/no-paths",
                    "paths": ["packages/{packageName}"],
                }
            ],
            source_map=source_map,
        )

        expanded = ok_value(result)
        assert dump(expanded.conventions[0]) == {
            "name": "no-paths",
            "description": "x",
            "paths": ["packages/{packageName}"],
            "must": {"haveFiles": ["README.md"]},
        }
        assert expanded.identifiers == ["common/no-paths"]

    def test_flows_placeholders_supplied_at_use_site_to_expanded_convention(self) -> None:
        source_map = build_source_map(
            {
                "common": [
                    {
                        "name": "provider-barrel",
                        "description": "x",
                        "must": {"export": ["${providerId}"]},
                    }
                ]
            }
        )

        result = expand_references(
            conventions=[
                {
                    "use": "common/provider-barrel",
                    "paths": "packages/openai/src/index.ts",
                    "placeholders": {"providerId": "openai"},
                }
            ],
            source_map=source_map,
        )

        expanded = ok_value(result)
        assert dump(expanded.conventions[0])["placeholders"] == {"providerId": "openai"}

    def test_replaces_inherited_arrays_with_override_arrays(self) -> None:
        source_map = build_source_map(
            {
                "common": [
                    {
                        "name": "with-excludes",
                        "description": "x",
                        "paths": "src/*.ts",
                        "excludeFiles": ["src/inherited.ts"],
                        "must": {"haveType": "file"},
                    }
                ]
            }
        )

        result = expand_references(
            conventions=[
                {
                    "use": "common/with-excludes",
                    "excludeFiles": ["src/override.ts"],
                }
            ],
            source_map=source_map,
        )

        expanded = ok_value(result)
        assert expanded.conventions[0].excludeFiles == ["src/override.ts"]

    def test_clears_inherited_array_when_override_supplies_empty_array(self) -> None:
        source_map = build_source_map(
            {
                "common": [
                    {
                        "name": "with-excludes",
                        "description": "x",
                        "paths": "src/*.ts",
                        "excludeFiles": ["src/inherited.ts"],
                        "must": {"haveType": "file"},
                    }
                ]
            }
        )

        result = expand_references(
            conventions=[{"use": "common/with-excludes", "excludeFiles": []}],
            source_map=source_map,
        )

        expanded = ok_value(result)
        assert expanded.conventions[0].excludeFiles == []

    def test_recursively_merges_nested_must_predicates_without_dropping_keys(self) -> None:
        source_map = build_source_map(
            {
                "common": [
                    {
                        "name": "merge-must",
                        "description": "x",
                        "paths": "src/*.ts",
                        "must": {"export": ["foo"]},
                    }
                ]
            }
        )

        result = expand_references(
            conventions=[
                {
                    "use": "common/merge-must",
                    "must": {"exportTypes": ["Bar"]},
                }
            ],
            source_map=source_map,
        )

        expanded = ok_value(result)
        assert dump(expanded.conventions[0])["must"] == {
            "export": ["foo"],
            "exportTypes": ["Bar"],
        }

    def test_recursively_merges_nested_must_not_predicates_without_dropping_keys(self) -> None:
        source_map = build_source_map(
            {
                "common": [
                    {
                        "name": "merge-must-not",
                        "description": "x",
                        "paths": "src/*.ts",
                        "mustNot": {"export": ["debug"]},
                    }
                ]
            }
        )

        result = expand_references(
            conventions=[
                {
                    "use": "common/merge-must-not",
                    "mustNot": {"exportTypes": ["Internal"]},
                }
            ],
            source_map=source_map,
        )

        expanded = ok_value(result)
        assert dump(expanded.conventions[0])["mustNot"] == {
            "export": ["debug"],
            "exportTypes": ["Internal"],
        }

    def test_replaces_primitive_values_like_severity(self) -> None:
        source_map = build_source_map(
            {
                "common": [
                    {
                        "name": "primitive-replace",
                        "description": "x",
                        "paths": "src/*.ts",
                        "severity": "error",
                        "must": {"haveType": "file"},
                    }
                ]
            }
        )

        result = expand_references(
            conventions=[
                {
                    "use": "common/primitive-replace",
                    "severity": "warning",
                }
            ],
            source_map=source_map,
        )

        expanded = ok_value(result)
        assert expanded.conventions[0].severity == "warning"

    def test_object_ref_errors_when_no_inherited_or_override_paths_exist(self) -> None:
        source_map = build_source_map(
            {
                "common": [
                    {
                        "name": "no-paths",
                        "description": "x",
                        "must": {"haveType": "file"},
                    }
                ]
            }
        )

        result = expand_references(conventions=[{"use": "common/no-paths"}], source_map=source_map)

        assert err_error(result) == (
            'Convention "common/no-paths" referenced in conventions[0] has no "paths". '
            "Either the reusable convention must declare paths, or the override must "
            "supply paths."
        )

    def test_expands_string_reference_nested_inside_hand_written_must_array(self) -> None:
        source_map = build_source_map(
            {
                "common": [
                    {
                        "name": "needs-readme",
                        "description": "Block requiring a README.md.",
                        "must": {"haveFiles": ["README.md"]},
                    }
                ]
            }
        )

        result = expand_references(
            conventions=[
                {
                    "paths": "packages/{packageName}",
                    "must": [{"must": {"haveType": "directory"}}, "common/needs-readme"],
                }
            ],
            source_map=source_map,
        )

        expanded = ok_value(result)
        must = dump(expanded.conventions[0])["must"]
        assert must[1] == {
            "name": "needs-readme",
            "description": "Block requiring a README.md.",
            "must": {"haveFiles": ["README.md"]},
        }

    def test_expands_must_not_string_reference_nested_inside_must_array(self) -> None:
        source_map = build_source_map(
            {
                "common": [
                    {
                        "name": "no-debug",
                        "description": "Block forbidding debug exports.",
                        "mustNot": {"exportConstants": ["debug"]},
                    }
                ]
            }
        )

        result = expand_references(
            conventions=[
                {
                    "paths": "packages/{packageName}",
                    "must": ["common/no-debug"],
                }
            ],
            source_map=source_map,
        )

        expanded = ok_value(result)
        assert dump(expanded.conventions[0])["must"][0] == {
            "name": "no-debug",
            "description": "Block forbidding debug exports.",
            "mustNot": {"exportConstants": ["debug"]},
        }

    def test_errors_when_string_reference_inside_must_points_at_reusable_with_paths(
        self,
    ) -> None:
        source_map = build_source_map(
            {
                "common": [
                    {
                        "name": "with-paths",
                        "description": "x",
                        "paths": "src/*.ts",
                        "must": {"haveType": "file"},
                    }
                ]
            }
        )

        result = expand_references(
            conventions=[
                {
                    "paths": "packages/{packageName}",
                    "must": ["common/with-paths"],
                }
            ],
            source_map=source_map,
        )

        error = err_error(result)
        assert "conventions[0].must[0]" in error
        assert '"paths"' in error
        assert "top-level-only" in error

    def test_expands_use_ref_nested_inside_hand_written_must_array(self) -> None:
        source_map = build_source_map(
            {
                "common": [
                    {
                        "name": "needs-readme",
                        "description": "Block requiring a README.md.",
                        "must": {"haveFiles": ["README.md"]},
                    }
                ]
            }
        )

        result = expand_references(
            conventions=[
                {
                    "paths": "packages/{packageName}",
                    "must": [
                        {"must": {"haveType": "directory"}},
                        {"use": "common/needs-readme"},
                    ],
                }
            ],
            source_map=source_map,
        )

        expanded = ok_value(result)
        assert dump(expanded.conventions[0])["must"][1] == {
            "name": "needs-readme",
            "description": "Block requiring a README.md.",
            "must": {"haveFiles": ["README.md"]},
        }

    def test_deep_merges_override_must_inside_must_array(self) -> None:
        source_map = build_source_map(
            {
                "common": [
                    {
                        "name": "base-block",
                        "description": "x",
                        "must": {"haveFiles": ["README.md"]},
                    }
                ]
            }
        )

        result = expand_references(
            conventions=[
                {
                    "paths": "packages/{packageName}",
                    "must": [
                        {
                            "use": "common/base-block",
                            "for": {"files": "{packageName}/index.ts"},
                            "must": {"exportTypes": ["Public"]},
                        }
                    ],
                }
            ],
            source_map=source_map,
        )

        expanded = ok_value(result)
        assert dump(expanded.conventions[0])["must"][0] == {
            "name": "base-block",
            "description": "x",
            "for": {"files": "{packageName}/index.ts"},
            "must": {"haveFiles": ["README.md"], "exportTypes": ["Public"]},
        }

    def test_deep_merges_override_must_not_inside_must_array(self) -> None:
        source_map = build_source_map(
            {
                "common": [
                    {
                        "name": "base-block",
                        "description": "x",
                        "mustNot": {"export": ["debug"]},
                    }
                ]
            }
        )

        result = expand_references(
            conventions=[
                {
                    "paths": "packages/{packageName}",
                    "must": [
                        {
                            "use": "common/base-block",
                            "mustNot": {"exportTypes": ["Internal"]},
                        }
                    ],
                }
            ],
            source_map=source_map,
        )

        expanded = ok_value(result)
        assert dump(expanded.conventions[0])["must"][0] == {
            "name": "base-block",
            "description": "x",
            "mustNot": {"export": ["debug"], "exportTypes": ["Internal"]},
        }

    def test_errors_when_must_use_ref_points_to_reusable_with_severity(self) -> None:
        source_map = build_source_map(
            {
                "common": [
                    {
                        "name": "with-severity",
                        "description": "x",
                        "severity": "warning",
                        "must": {"haveType": "file"},
                    }
                ]
            }
        )

        result = expand_references(
            conventions=[
                {
                    "paths": "packages/{packageName}",
                    "must": [{"use": "common/with-severity"}],
                }
            ],
            source_map=source_map,
        )

        error = err_error(result)
        assert "conventions[0].must[0]" in error
        assert '"severity"' in error
        assert "top-level-only" in error

    def test_emits_unknown_source_error_scoped_to_must_block_location(self) -> None:
        result = expand_references(
            conventions=[
                {
                    "paths": "packages/{packageName}",
                    "must": [{"use": "missing/foo"}],
                }
            ],
            source_map={},
        )

        error = err_error(result)
        assert "conventions[0].must[0]" in error
        assert 'Unknown convention source "missing"' in error

    def test_includes_conventions_dot_index_in_path_of_validation_errors(self) -> None:
        source_map = build_source_map(
            {
                "common": [
                    {
                        "name": "ok",
                        "description": "x",
                        "paths": "src/*.ts",
                        "must": {"haveType": "file"},
                    }
                ]
            }
        )

        result = expand_references(
            conventions=[{"use": "common/ok", "severity": "bogus"}],
            source_map=source_map,
        )

        error = err_error(result)
        assert "conventions.0" in error
        assert "severity" in error


class TestDeepMerge:
    def test_recursively_merges_plain_dicts(self) -> None:
        result = deep_merge(
            base={"must": {"export": ["foo"]}},
            override={"must": {"exportTypes": ["Bar"]}},
        )

        assert result == {"must": {"export": ["foo"], "exportTypes": ["Bar"]}}

    def test_replaces_arrays_without_concatenating(self) -> None:
        result = deep_merge(
            base={"excludeFiles": ["a.py"]},
            override={"excludeFiles": ["b.py"]},
        )

        assert result == {"excludeFiles": ["b.py"]}

    def test_override_none_replaces_when_present(self) -> None:
        result = deep_merge(base={"description": "base"}, override={"description": None})

        assert result == {"description": None}
