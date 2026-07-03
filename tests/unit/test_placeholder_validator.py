from __future__ import annotations

from typing import Any

from konpy.config.errors import Err, Ok
from konpy.config.placeholder_validator import validate_placeholders
from konpy.config.schema import ConventionV1


def convention(data: dict[str, Any]) -> ConventionV1:
    return ConventionV1.model_validate(data)


def error(result: object) -> str:
    assert isinstance(result, Err)
    return result.error


class TestValidatePlaceholders:
    def test_accepts_placeholder_declared_in_paths_and_used_in_must_have_files(self) -> None:
        conventions = [
            convention(
                {
                    "name": "package-must-have-readme",
                    "paths": ["packages/{packageName}"],
                    "must": {"haveFiles": ["${packageName}/README.md"]},
                }
            )
        ]

        result = validate_placeholders(
            conventions=conventions,
            identifiers=["common/package-must-have-readme"],
        )

        assert result == Ok(None)

    def test_rejects_placeholder_used_in_must_but_absent_from_paths(self) -> None:
        conventions = [
            convention(
                {
                    "name": "broken",
                    "paths": ["packages/{packageName}"],
                    "must": {"haveFiles": ["${componentName}.tsx"]},
                }
            )
        ]

        result = validate_placeholders(conventions=conventions, identifiers=["broken"])

        assert error(result) == (
            'Convention "broken" references "${componentName}" in must.haveFiles, but '
            'neither paths nor placeholders declare "{componentName}".'
        )

    def test_rejects_placeholder_used_in_must_not_but_absent_from_paths(self) -> None:
        conventions = [
            convention(
                {
                    "name": "broken",
                    "paths": ["packages/{packageName}"],
                    "mustNot": {"exportConstants": ["${componentName}Debug"]},
                }
            )
        ]

        result = validate_placeholders(conventions=conventions, identifiers=["broken"])

        assert error(result) == (
            'Convention "broken" references "${componentName}" in mustNot.exportConstants, '
            'but neither paths nor placeholders declare "{componentName}".'
        )

    def test_reports_only_missing_placeholder_when_multiple_are_used(self) -> None:
        conventions = [
            convention(
                {
                    "name": "partial",
                    "paths": ["packages/{packageName}"],
                    "must": {"haveFiles": ["${packageName}/${missing}.ts"]},
                }
            )
        ]

        result = validate_placeholders(conventions=conventions, identifiers=["partial"])

        assert '"${missing}"' in error(result)
        assert '"${packageName}"' not in error(result)

    def test_detects_placeholder_inside_object_form_export_entry(self) -> None:
        conventions = [
            convention(
                {
                    "name": "object-export",
                    "paths": ["src/{x}"],
                    "must": {"export": [{"name": "${X}", "from": "${Y}"}]},
                }
            )
        ]

        result = validate_placeholders(conventions=conventions, identifiers=["object-export"])

        assert '"${X}"' in error(result)
        assert "must.export" in error(result)

    def test_detects_placeholder_inside_nested_must_block_predicate(self) -> None:
        conventions = [
            convention(
                {
                    "name": "block-form",
                    "paths": ["packages/{packageName}"],
                    "must": [{"if": {"hasFile": "${missing}.ts"}, "must": {"haveFiles": ["x"]}}],
                }
            )
        ]

        result = validate_placeholders(conventions=conventions, identifiers=["block-form"])

        assert '"${missing}"' in error(result)
        assert "must.if.hasFile" in error(result)

    def test_detects_placeholder_inside_nested_must_block_must_not_predicate(self) -> None:
        conventions = [
            convention(
                {
                    "name": "block-form",
                    "paths": ["packages/{packageName}"],
                    "must": [{"mustNot": {"exportConstants": ["${missing}Debug"]}}],
                }
            )
        ]

        result = validate_placeholders(conventions=conventions, identifiers=["block-form"])

        assert '"${missing}"' in error(result)
        assert "mustNot.exportConstants" in error(result)

    def test_scans_single_string_paths_value_for_declared_placeholders(self) -> None:
        conventions = [
            convention(
                {
                    "name": "single-path",
                    "paths": "packages/{packageName}",
                    "must": {"haveFiles": ["${packageName}/README.md"]},
                }
            )
        ]

        result = validate_placeholders(conventions=conventions, identifiers=["single-path"])

        assert result == Ok(None)

    def test_uses_fallback_identifier_when_supplied(self) -> None:
        conventions = [
            convention(
                {
                    "paths": ["src/{x}"],
                    "must": {"haveFiles": ["${missing}.ts"]},
                }
            )
        ]

        result = validate_placeholders(conventions=conventions, identifiers=["conventions[0]"])

        assert 'Convention "conventions[0]"' in error(result)

    def test_uses_ref_identifier_for_ref_expanded_conventions(self) -> None:
        conventions = [
            convention(
                {
                    "name": "package-must-have-readme",
                    "paths": ["packages/{packageName}"],
                    "must": {"haveFiles": ["${componentName}.tsx"]},
                }
            )
        ]

        result = validate_placeholders(
            conventions=conventions,
            identifiers=["common/package-must-have-readme"],
        )

        assert 'Convention "common/package-must-have-readme"' in error(result)

    def test_reports_placeholders_inside_placeholder_satisfies(self) -> None:
        conventions = [
            convention(
                {
                    "name": "satisfies",
                    "paths": ["packages/{packageName}"],
                    "must": [
                        {
                            "if": {"placeholderSatisfies": "${missing}.matches(/foo/)"},
                            "must": {"haveFiles": ["index.ts"]},
                        }
                    ],
                }
            )
        ]

        result = validate_placeholders(conventions=conventions, identifiers=["satisfies"])

        assert "must.if.placeholderSatisfies" in error(result)

    def test_reports_placeholders_inside_for_files_string_and_array_forms(self) -> None:
        string_form = [
            convention(
                {
                    "name": "for-string",
                    "paths": ["packages/{packageName}"],
                    "must": [{"for": {"files": "${missing}.ts"}, "must": {"haveFiles": ["x"]}}],
                }
            )
        ]
        array_form = [
            convention(
                {
                    "name": "for-array",
                    "paths": ["packages/{packageName}"],
                    "must": [{"for": {"files": ["${missing}.ts"]}, "must": {"haveFiles": ["x"]}}],
                }
            )
        ]

        assert isinstance(
            validate_placeholders(conventions=string_form, identifiers=["for-string"]),
            Err,
        )
        assert isinstance(
            validate_placeholders(conventions=array_form, identifiers=["for-array"]),
            Err,
        )

    def test_detects_placeholders_inside_class_extend_and_implement_entries(self) -> None:
        conventions = [
            convention(
                {
                    "name": "classes",
                    "paths": ["src/{x}"],
                    "must": {
                        "exportClasses": [
                            {
                                "name": "Foo",
                                "extend": {"type": "${missing}", "allowOmissions": True},
                                "implement": ["${alsoMissing}"],
                            }
                        ]
                    },
                }
            )
        ]

        result = validate_placeholders(conventions=conventions, identifiers=["classes"])

        assert '"${missing}"' in error(result)
        assert '"${alsoMissing}"' in error(result)

    def test_detects_placeholders_inside_declaration_predicates(self) -> None:
        conventions = [
            convention(
                {
                    "name": "declarations",
                    "paths": ["src/{x}"],
                    "must": {
                        "declareTypes": [{"name": "${missingType}"}],
                        "declareConstants": ["${missingConstant}"],
                        "declareFunctions": [
                            {
                                "name": "create${missingFunction}",
                                "receiveParamOfType": "${missingParam}",
                                "receiveParamsOfTypes": ["${missingParamAtIndex}"],
                                "returnValueOfType": "${missingReturn}",
                            }
                        ],
                        "declareInterfaces": [
                            {
                                "name": "Local",
                                "extend": {"type": "${missingExtend}", "allowOmissions": True},
                            }
                        ],
                        "declareClasses": [
                            {"name": "LocalClass", "implement": ["${missingImplement}"]}
                        ],
                        "useDeclarationOrder": ["${missingOrder}"],
                    },
                }
            )
        ]

        result = validate_placeholders(conventions=conventions, identifiers=["declarations"])
        result_error = error(result)

        assert '"${missingType}"' in result_error
        assert '"${missingParamAtIndex}"' in result_error
        assert "must.declareTypes" in result_error
        assert "must.declareFunctions" in result_error

    def test_detects_placeholders_inside_import_from(self) -> None:
        conventions = [
            convention(
                {
                    "name": "imports",
                    "paths": ["src/{x}"],
                    "must": {"importFrom": "@scope/${missingPackage}"},
                }
            )
        ]

        result = validate_placeholders(conventions=conventions, identifiers=["imports"])

        assert '"${missingPackage}"' in error(result)
        assert "must.importFrom" in error(result)

    def test_treats_for_files_declarations_as_in_scope_for_block_predicates(self) -> None:
        conventions = [
            convention(
                {
                    "name": "for-declares",
                    "paths": "packages/{providerId}",
                    "must": [
                        {
                            "for": {"files": "*/${providerId}-{modelKind:segments(2)}-model.ts"},
                            "must": {"exportFunctions": ["create${providerId}${modelKind}"]},
                        }
                    ],
                }
            )
        ]

        result = validate_placeholders(conventions=conventions, identifiers=["for-declares"])

        assert result == Ok(None)

    def test_treats_constraint_syntax_in_paths_as_valid_declaration(self) -> None:
        conventions = [
            convention(
                {
                    "name": "constraint-paths",
                    "paths": "packages/{providerId:matches(^[a-z]+$)}",
                    "must": {"haveFiles": ["${providerId}.ts"]},
                }
            )
        ]

        result = validate_placeholders(conventions=conventions, identifiers=["constraint-paths"])

        assert result == Ok(None)

    def test_accepts_usage_backed_by_static_placeholders_entry(self) -> None:
        conventions = [
            convention(
                {
                    "name": "static-providers",
                    "paths": "packages/openai/src/index.ts",
                    "placeholders": {"providerId": "openai"},
                    "must": {"export": ["${providerId}"]},
                }
            )
        ]

        result = validate_placeholders(conventions=conventions, identifiers=["static-providers"])

        assert result == Ok(None)

    def test_rejects_name_declared_in_both_paths_and_placeholders(self) -> None:
        conventions = [
            convention(
                {
                    "name": "double-declared",
                    "paths": "packages/{providerId}/src/index.ts",
                    "placeholders": {"providerId": "openai"},
                    "must": {"export": ["${providerId}"]},
                }
            )
        ]

        result = validate_placeholders(conventions=conventions, identifiers=["double-declared"])

        assert (
            'Convention "double-declared" declares placeholder "providerId" both in paths '
            '(as "{providerId}") and in placeholders. Pick one.'
        ) in error(result)

    def test_reports_each_missing_name_once_preserving_first_seen_key(self) -> None:
        conventions = [
            convention(
                {
                    "name": "repeat",
                    "paths": "src/{x}",
                    "must": {
                        "haveFiles": ["${missing}.py"],
                        "export": ["${missing}"],
                    },
                }
            )
        ]

        result = validate_placeholders(conventions=conventions, identifiers=["repeat"])

        assert error(result).count('"${missing}"') == 1
        assert "must.haveFiles" in error(result)

    def test_returns_ok_when_no_must_placeholders_are_used(self) -> None:
        conventions = [
            convention(
                {
                    "name": "static",
                    "paths": "src/lib",
                    "must": {"haveType": "directory", "haveFiles": ["index.ts"]},
                }
            )
        ]

        result = validate_placeholders(conventions=conventions, identifiers=["static"])

        assert result == Ok(None)
