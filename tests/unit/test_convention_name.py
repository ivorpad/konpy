from typing import Any

from pydantic import TypeAdapter

from konsistent.config.schema import MustBlockV1, MustPredicatesV1
from konsistent.core.convention_name import generate_convention_name
from konsistent.predicates.registry import PredicateRegistry, builtin_predicate_registry


def must(payload: dict) -> MustPredicatesV1:
    return MustPredicatesV1.model_validate(payload)


def block(payload: dict) -> MustBlockV1:
    return MustBlockV1.model_validate(payload)


class TestHaveType:
    def test_generates_must_be_directory(self) -> None:
        assert generate_convention_name(must=must({"haveType": "directory"})) == "must-be-directory"

    def test_generates_must_be_file(self) -> None:
        assert generate_convention_name(must=must({"haveType": "file"})) == "must-be-file"


class TestHaveFiles:
    def test_generates_first_file_kebab(self) -> None:
        assert generate_convention_name(must=must({"haveFiles": ["index.py"]})) == (
            "must-have-index-py"
        )

    def test_appends_and_more_for_multiple_files(self) -> None:
        assert (
            generate_convention_name(must=must({"haveFiles": ["index.py", "types.py"]}))
            == "must-have-index-py-and-more"
        )

    def test_converts_path_separators_to_hyphens(self) -> None:
        assert (
            generate_convention_name(must=must({"haveFiles": ["src/index.py"]}))
            == "must-have-src-index-py"
        )


class TestExport:
    def test_generates_must_export_name_kebab(self) -> None:
        assert generate_convention_name(must=must({"export": ["activate"]})) == (
            "must-export-activate"
        )

    def test_appends_and_more_for_multiple_exports(self) -> None:
        assert (
            generate_convention_name(must=must({"export": ["activate", "deactivate"]}))
            == "must-export-activate-and-more"
        )

    def test_strips_template_expressions_and_converts_to_kebab(self) -> None:
        assert (
            generate_convention_name(
                must=must({"export": ["create${name.toPascalCase()}Adapter"]})
            )
            == "must-export-create-adapter"
        )

    def test_falls_back_when_template_stripping_leaves_empty_string(self) -> None:
        assert generate_convention_name(must=must({"export": ["${providerId}"]})) == "must-export"


class TestDeclarePredicates:
    def test_declare_types(self) -> None:
        assert (
            generate_convention_name(must=must({"declareTypes": ["MyType"]}))
            == "must-declare-my-type-type"
        )

    def test_declare_constants(self) -> None:
        assert (
            generate_convention_name(must=must({"declareConstants": ["pluginId"]}))
            == "must-declare-plugin-id-constant"
        )

    def test_declare_functions_object(self) -> None:
        assert (
            generate_convention_name(
                must=must({"declareFunctions": [{"name": "create${name.toPascalCase()}Adapter"}]})
            )
            == "must-declare-create-adapter-function"
        )

    def test_declare_classes_object(self) -> None:
        assert (
            generate_convention_name(
                must=must({"declareClasses": [{"name": "${name.toPascalCase()}Adapter"}]})
            )
            == "must-declare-adapter-class"
        )

    def test_declare_interfaces_object(self) -> None:
        assert (
            generate_convention_name(
                must=must({"declareInterfaces": [{"name": "${id.toPascalCase()}Provider"}]})
            )
            == "must-declare-provider-interface"
        )


class TestExportPredicates:
    def test_export_types(self) -> None:
        assert (
            generate_convention_name(must=must({"exportTypes": ["MyType"]}))
            == "must-export-my-type-type"
        )

    def test_export_types_template(self) -> None:
        assert (
            generate_convention_name(
                must=must({"exportTypes": ["${id.toPascalCase()}Provider"]})
            )
            == "must-export-provider-type"
        )

    def test_export_types_object(self) -> None:
        assert (
            generate_convention_name(
                must=must({"exportTypes": [{"name": "${id.toPascalCase()}Provider"}]})
            )
            == "must-export-provider-type"
        )

    def test_export_constants(self) -> None:
        assert (
            generate_convention_name(must=must({"exportConstants": ["pluginId"]}))
            == "must-export-plugin-id-constant"
        )

    def test_export_functions(self) -> None:
        assert (
            generate_convention_name(
                must=must({"exportFunctions": [{"name": "create${name.toPascalCase()}Adapter"}]})
            )
            == "must-export-create-adapter-function"
        )

    def test_export_functions_strips_templates(self) -> None:
        assert (
            generate_convention_name(
                must=must(
                    {"exportFunctions": [{"name": "create${serviceName.toPascalCase()}Service"}]}
                )
            )
            == "must-export-create-service-function"
        )

    def test_export_classes(self) -> None:
        assert (
            generate_convention_name(
                must=must({"exportClasses": [{"name": "${name.toPascalCase()}Adapter"}]})
            )
            == "must-export-adapter-class"
        )

    def test_export_interfaces(self) -> None:
        assert (
            generate_convention_name(
                must=must(
                    {"exportInterfaces": [{"name": "${id.toPascalCase()}Provider"}]}
                )
            )
            == "must-export-provider-interface"
        )


class TestImportPredicates:
    def test_import_alias_key(self) -> None:
        assert (
            generate_convention_name(
                must=must({"import": [{"name": "BaseAdapter", "from": "core"}]})
            )
            == "must-import-base-adapter"
        )

    def test_import_from(self) -> None:
        assert (
            generate_convention_name(must=must({"importFrom": "collections.abc"}))
            == "must-import-from-collections-abc"
        )

    def test_import_from_strips_templates(self) -> None:
        assert (
            generate_convention_name(must=must({"importFrom": ".${packageName}"}))
            == "must-import-from"
        )

    def test_import_types(self) -> None:
        assert (
            generate_convention_name(
                must=must(
                    {"importTypes": [{"name": "ProviderV1", "from": ".types"}]}
                )
            )
            == "must-import-provider-v1-type"
        )


class TestImportSourcePredicates:
    def test_current_dir_import_names(self) -> None:
        assert (
            generate_convention_name(must=must({"importFromCurrentDir": True}))
            == "must-import-from-current-dir"
        )
        assert (
            generate_convention_name(must=must({"importFromCurrentDir": False}))
            == "must-not-import-from-current-dir"
        )

    def test_parent_and_external_import_names(self) -> None:
        assert (
            generate_convention_name(must=must({"importFromParents": True}))
            == "must-import-from-parents"
        )
        assert (
            generate_convention_name(must=must({"importFromExternals": False}))
            == "must-not-import-from-externals"
        )

    def test_type_import_source_names(self) -> None:
        assert (
            generate_convention_name(must=must({"importTypesFromCurrentDir": True}))
            == "must-import-type-from-current-dir"
        )
        assert (
            generate_convention_name(must=must({"importTypesFromParents": False}))
            == "must-not-import-type-from-parents"
        )
        assert (
            generate_convention_name(must=must({"importTypesFromExternals": True}))
            == "must-import-type-from-externals"
        )


class TestMustNot:
    def test_generates_negated_names_for_must_not_predicates(self) -> None:
        assert (
            generate_convention_name(must_not=must({"exportConstants": ["debug"]}))
            == "must-not-export-debug-constant"
        )

    def test_generates_logical_names_for_negated_boolean_predicates(self) -> None:
        assert (
            generate_convention_name(must_not=must({"importFromCurrentDir": True}))
            == "must-not-import-from-current-dir"
        )
        assert (
            generate_convention_name(must_not=must({"importFromCurrentDir": False}))
            == "must-import-from-current-dir"
        )
        assert (
            generate_convention_name(must_not=must({"importTypesFromCurrentDir": True}))
            == "must-not-import-type-from-current-dir"
        )
        assert (
            generate_convention_name(must_not=must({"importTypesFromCurrentDir": False}))
            == "must-import-type-from-current-dir"
        )
        assert (
            generate_convention_name(must_not=must({"importFrom": "react"}))
            == "must-not-import-from-react"
        )


class TestUseDeclarationOrder:
    def test_generates_declaration_order_names(self) -> None:
        assert (
            generate_convention_name(
                must=must(
                    {"useDeclarationOrder": ["create${name.toPascalCase()}"]}
                )
            )
            == "must-use-create-declaration-order"
        )


class TestAndMoreSuffix:
    def test_appends_when_must_object_has_multiple_predicate_keys(self) -> None:
        assert (
            generate_convention_name(
                must=must({"export": ["activate"], "exportConstants": ["pluginId"]})
            )
            == "must-export-activate-and-more"
        )

    def test_appends_when_predicate_array_has_multiple_items(self) -> None:
        assert (
            generate_convention_name(must=must({"export": ["activate", "deactivate"]}))
            == "must-export-activate-and-more"
        )

    def test_appends_when_both_conditions_are_true(self) -> None:
        assert (
            generate_convention_name(
                must=must(
                    {
                        "export": ["activate", "deactivate"],
                        "exportConstants": ["pluginId"],
                    }
                )
            )
            == "must-export-activate-and-more"
        )


class TestMustBlockArray:
    def test_uses_first_block_first_predicate(self) -> None:
        assert (
            generate_convention_name(
                must=[
                    block({"must": {"haveFiles": ["${componentName}.py"]}}),
                    block({"must": {"export": ["describe"]}}),
                ]
            )
            == "must-have-py"
        )

    def test_handles_template_only_file_name_in_have_files(self) -> None:
        assert (
            generate_convention_name(must=[block({"must": {"haveFiles": ["${name}.py"]}})])
            == "must-have-py"
        )

    def test_uses_must_not_when_first_block_has_no_must(self) -> None:
        assert (
            generate_convention_name(must=[block({"mustNot": {"export": ["debug"]}})])
            == "must-not-export-debug"
        )


class TestEdgeCases:
    def test_returns_convention_for_empty_must_object(self) -> None:
        assert generate_convention_name(must=must({})) == "convention"

    def test_handles_export_with_empty_name_after_template_strip_and_multiple_keys(self) -> None:
        assert (
            generate_convention_name(
                must=must(
                    {
                        "export": ["${providerId}"],
                        "exportTypes": ["${providerId.toPascalCase()}Provider"],
                    }
                )
            )
            == "must-export-and-more"
        )


class TestMatchContent:
    def test_generates_match_content_names(self) -> None:
        assert (
            generate_convention_name(must=must({"matchContent": ["SPDX-License-Identifier"]}))
            == "must-match-content"
        )

    def test_generates_must_not_match_content_names(self) -> None:
        assert (
            generate_convention_name(must_not=must({"matchContent": ["TODO"]}))
            == "must-not-match-content"
        )

    def test_appends_and_more_for_multiple_match_content_patterns(self) -> None:
        assert (
            generate_convention_name(
                must=must({"matchContent": ["SPDX-License-Identifier", "Copyright"]})
            )
            == "must-match-content-and-more"
        )


class TestHavePairedFile:
    def test_generates_have_paired_file_names(self) -> None:
        assert (
            generate_convention_name(must=must({"havePairedFile": "tests/test_${name}.py"}))
            == "must-have-paired-tests-test-py"
        )

    def test_generates_must_not_have_paired_file_names(self) -> None:
        assert (
            generate_convention_name(must_not=must({"havePairedFile": "tests/test_${name}.py"}))
            == "must-not-have-paired-tests-test-py"
        )


class TestHaveDocstrings:
    def test_generates_have_docstrings_names(self) -> None:
        assert (
            generate_convention_name(must=must({"haveDocstrings": True}))
            == "must-have-docstrings"
        )

    def test_generates_must_not_have_docstrings_names(self) -> None:
        assert (
            generate_convention_name(must_not=must({"haveDocstrings": True}))
            == "must-not-have-docstrings"
        )


class TestAnnotateFunctions:
    def test_generates_annotate_functions_names(self) -> None:
        assert (
            generate_convention_name(must=must({"annotateFunctions": True}))
            == "must-annotate-functions"
        )

    def test_generates_must_not_annotate_functions_names(self) -> None:
        assert (
            generate_convention_name(must_not=must({"annotateFunctions": True}))
            == "must-not-annotate-functions"
        )


def plugin_name_registry(*, key: str, value_model: Any = str) -> PredicateRegistry:
    base = builtin_predicate_registry()
    return PredicateRegistry(
        handlers=base.handlers,
        ast_predicates=base.ast_predicates,
        item_level_must_not_predicates=base.item_level_must_not_predicates,
        plugin_value_adapters={key: TypeAdapter(value_model)},
        plugin_forbidden_messages={},
        plugin_validate_placeholders={key: True},
        plugin_origins={},
    )


def plugin_must(payload: dict, *, key: str = "acmeRule") -> MustPredicatesV1:
    registry = plugin_name_registry(key=key)
    return MustPredicatesV1.model_validate(payload, context=registry.validation_context())


class TestPluginConventionNames:
    def test_generates_positive_plugin_predicate_name_from_key(self) -> None:
        assert (
            generate_convention_name(must=plugin_must({"acmeRule": "expected"}))
            == "must-acme-rule"
        )

    def test_generates_negative_plugin_predicate_name_from_key(self) -> None:
        assert (
            generate_convention_name(must_not=plugin_must({"acmeRule": "expected"}))
            == "must-not-acme-rule"
        )

    def test_appends_and_more_for_plugin_predicate_with_multiple_keys(self) -> None:
        assert (
            generate_convention_name(
                must=plugin_must(
                    {"acmeRule": "expected", "haveFiles": ["README.md"]},
                    key="acmeRule",
                )
            )
            == "must-have-README-md-and-more"
        )

    def test_converts_non_camel_plugin_key_to_kebab(self) -> None:
        assert (
            generate_convention_name(
                must=plugin_must({"acme_rule": "expected"}, key="acme_rule")
            )
            == "must-acme-rule"
        )
