from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import TypeAdapter

from konsistent.config.schema import ConfigV1
from konsistent.core.context import PredicateContext
from konsistent.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konsistent.core.filesystem import FakeFileSystem, FileSystem
from konsistent.core.runner import run
from konsistent.predicates.registry import (
    PredicateHandler,
    PredicateRegistry,
    builtin_predicate_registry,
)
from konsistent.python_ast.structure import PyFileStructure


def config(conventions: list[dict], **extra: object) -> ConfigV1:
    return ConfigV1.model_validate(
        {
            "version": "v1",
            "conventions": conventions,
            **extra,
        }
    )


class CountingFileSystem(FakeFileSystem):
    def __init__(
        self,
        *,
        contents: Mapping[str, str],
        files: list[str] | None = None,
        directories: list[str] | None = None,
    ) -> None:
        super().__init__(
            contents=contents,
            files=files or [],
            directories=directories or [],
        )
        self.read_file_calls: list[str] = []

    def read_file(self, path: str) -> str:
        self.read_file_calls.append(path)
        return super().read_file(path)


class TestRunBasics:
    def test_returns_empty_result_for_empty_conventions(self) -> None:
        result = run(
            config=config([]),
            file_system=FakeFileSystem(),
        )

        assert result.diagnostics == []
        assert result.files_checked == 0
        assert result.duration_ms is not None
        assert result.duration_ms >= 0

    def test_checks_basic_must_predicates_over_matched_paths(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "source-files",
                        "paths": "src/**/*.py",
                        "must": {"haveType": "file"},
                    }
                ]
            ),
            file_system=FakeFileSystem(
                files=["src/index.py"],
                directories=["src/utils.py"],
            ),
        )

        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].file_path == "src/utils.py"
        assert result.diagnostics[0].predicate_name == "haveType"
        assert result.diagnostics[0].message == "Expected a file but found a directory"
        assert result.diagnostics[0].convention_name == "source-files"
        assert result.files_checked == 2

    def test_normalizes_paths_arrays(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "paths": ["src/*.py", "lib/*.py"],
                        "must": {"haveType": "file"},
                    }
                ]
            ),
            file_system=FakeFileSystem(files=["src/a.py", "lib/b.py"]),
        )

        assert result.diagnostics == []
        assert result.files_checked == 2

    def test_generates_convention_name_when_name_is_absent(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "paths": "src",
                        "must": {"haveType": "file"},
                    }
                ]
            ),
            file_system=FakeFileSystem(directories=["src"]),
        )

        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].convention_name == "must-be-file"

    def test_duration_ms_is_present(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "paths": "src/index.py",
                        "must": {"haveType": "file"},
                    }
                ]
            ),
            file_system=FakeFileSystem(files=["src/index.py"]),
        )

        assert isinstance(result.duration_ms, float)
        assert result.duration_ms >= 0


class TestPlaceholders:
    def test_resolves_captured_placeholders_in_predicate_values(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "module-exports",
                        "paths": "modules/{name}.py",
                        "must": {"export": ["${name.toPascalCase()}"]},
                    }
                ]
            ),
            file_system=FakeFileSystem(
                contents={"modules/user.py": "def User():\n    pass\n"},
            ),
        )

        assert result.diagnostics == []

    def test_uses_case_maps_for_placeholder_transforms(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "provider-exports",
                        "paths": "providers/{providerId}.py",
                        "must": {
                            "exportClasses": [
                                "${providerId.toPascalCase()}Provider"
                            ]
                        },
                    }
                ],
                kebabToPascalMap={"openai": "OpenAI"},
            ),
            file_system=FakeFileSystem(
                contents={
                    "providers/openai.py": "class OpenAIProvider:\n    pass\n",
                },
            ),
        )

        assert result.diagnostics == []

    def test_static_placeholders_are_available_in_predicates(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "static-placeholders",
                        "paths": "packages/openai",
                        "placeholders": {"providerId": "openai"},
                        "must": {"haveFiles": ["${providerId}.py"]},
                    }
                ]
            ),
            file_system=FakeFileSystem(
                files=["packages/openai/openai.py"],
                directories=["packages/openai"],
            ),
        )

        assert result.diagnostics == []

    def test_captured_placeholders_win_over_static_placeholders(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "captured-wins",
                        "paths": "packages/{name}",
                        "placeholders": {"name": "wrong"},
                        "must": {"haveFiles": ["${name}.py"]},
                    }
                ]
            ),
            file_system=FakeFileSystem(
                files=["packages/openai/openai.py"],
                directories=["packages/openai"],
            ),
        )

        assert result.diagnostics == []


class TestConditions:
    def test_evaluates_block_when_if_has_file_is_true(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "conditional",
                        "paths": "src/with.py",
                        "must": [
                            {
                                "if": {"hasFile": "schema.py"},
                                "must": {"haveType": "directory"},
                            }
                        ],
                    }
                ]
            ),
            file_system=FakeFileSystem(
                files=["src/with.py", "src/schema.py"],
            ),
        )

        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].message == "Expected a directory but found a file"

    def test_skips_block_when_if_has_file_is_false(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "conditional",
                        "paths": "src/without.py",
                        "must": [
                            {
                                "if": {"hasFile": "schema.py"},
                                "must": {"haveType": "directory"},
                            }
                        ],
                    }
                ]
            ),
            file_system=FakeFileSystem(files=["src/without.py"]),
        )

        assert result.diagnostics == []

    def test_evaluates_block_when_placeholder_satisfies_is_true(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "provider-rule",
                        "paths": "packages/{providerId}",
                        "must": [
                            {
                                "if": {
                                    "placeholderSatisfies": (
                                        "providerId:matches(^[a-z]+ai$)"
                                    )
                                },
                                "must": {"haveType": "file"},
                            }
                        ],
                    }
                ]
            ),
            file_system=FakeFileSystem(directories=["packages/openai"]),
        )

        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].file_path == "packages/openai"

    def test_skips_block_when_placeholder_satisfies_is_false(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "provider-rule",
                        "paths": "packages/{providerId}",
                        "must": [
                            {
                                "if": {
                                    "placeholderSatisfies": (
                                        "providerId:matches(^[a-z]+ai$)"
                                    )
                                },
                                "must": {"haveType": "file"},
                            }
                        ],
                    }
                ]
            ),
            file_system=FakeFileSystem(directories=["packages/google"]),
        )

        assert result.diagnostics == []

    def test_skips_block_when_placeholder_satisfies_is_malformed(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "provider-rule",
                        "paths": "packages/{providerId}",
                        "must": [
                            {
                                "if": {"placeholderSatisfies": "providerId:matches("},
                                "must": {"haveType": "file"},
                            }
                        ],
                    }
                ]
            ),
            file_system=FakeFileSystem(directories=["packages/openai"]),
        )

        assert result.diagnostics == []

    def test_supports_template_expansion_in_if_has_file(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "template-condition",
                        "paths": "src/{name}/index.py",
                        "must": [
                            {
                                "if": {"hasFile": "${name}_test.py"},
                                "must": {"haveType": "directory"},
                            }
                        ],
                    }
                ]
            ),
            file_system=FakeFileSystem(
                files=["src/auth/index.py", "src/auth/auth_test.py"],
            ),
        )

        assert len(result.diagnostics) == 1


class TestForBlocks:
    def test_expands_for_files_and_counts_children(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "component-tests",
                        "paths": "components/{name}",
                        "must": [
                            {
                                "for": {"files": "*.test.py"},
                                "must": {"haveType": "file"},
                            }
                        ],
                    }
                ]
            ),
            file_system=FakeFileSystem(
                files=["components/Button/Button.test.py"],
                directories=["components/Button"],
            ),
        )

        assert result.diagnostics == []
        assert result.files_checked == 2

    def test_silently_skips_for_block_when_no_children_match(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "component-tests",
                        "paths": "components/{name}",
                        "must": [
                            {
                                "for": {"files": "*.test.py"},
                                "must": {"haveType": "file"},
                            }
                        ],
                    }
                ]
            ),
            file_system=FakeFileSystem(directories=["components/Button"]),
        )

        assert result.diagnostics == []
        assert result.files_checked == 1

    def test_for_files_supports_arrays(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "component-tests",
                        "paths": "components/{name}",
                        "must": [
                            {
                                "for": {"files": ["*.test.py", "*.spec.py"]},
                                "must": {"haveType": "file"},
                            }
                        ],
                    }
                ]
            ),
            file_system=FakeFileSystem(
                files=[
                    "components/Button/Button.test.py",
                    "components/Button/Button.spec.py",
                ],
                directories=["components/Button"],
            ),
        )

        assert result.diagnostics == []
        assert result.files_checked == 3

    def test_parent_placeholders_win_over_child_captures(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "parent-wins",
                        "paths": "components/{name}",
                        "must": [
                            {
                                "for": {"files": "{name}.py"},
                                "must": {"haveFiles": ["${name}.txt"]},
                            }
                        ],
                    }
                ]
            ),
            file_system=FakeFileSystem(
                files=[
                    "components/Button/child.py",
                    "components/Button/Button.txt",
                ],
                directories=["components/Button"],
            ),
        )

        assert result.diagnostics == []

    def test_if_condition_is_evaluated_before_for_iteration(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "if-for",
                        "paths": "components/{name}",
                        "must": [
                            {
                                "if": {"hasFile": "${name}.test.py"},
                                "for": {"files": "${name}.test.py"},
                                "must": {"haveType": "directory"},
                            }
                        ],
                    }
                ]
            ),
            file_system=FakeFileSystem(
                files=["components/Button/Button.test.py"],
                directories=["components/Button"],
            ),
        )

        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].file_path == "components/Button/Button.test.py"


class TestExcludeFiles:
    def test_convention_level_exclude_files_skips_matching_file(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "exclude",
                        "paths": "src/*.py",
                        "excludeFiles": ["src/skipped.py"],
                        "must": {"haveType": "file"},
                    }
                ]
            ),
            file_system=FakeFileSystem(
                files=["src/kept.py"],
                directories=["src/skipped.py"],
            ),
        )

        assert result.diagnostics == []

    def test_convention_level_exclude_files_resolves_templates(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "exclude-template",
                        "paths": "packages/{name}/index.py",
                        "excludeFiles": ["packages/${name}/index.py"],
                        "must": {"haveType": "directory"},
                    }
                ]
            ),
            file_system=FakeFileSystem(files=["packages/openai/index.py"]),
        )

        assert result.diagnostics == []

    def test_block_level_exclude_files_without_for_skips_matching_file(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "block-exclude",
                        "paths": "src/*.py",
                        "must": [
                            {
                                "excludeFiles": ["special.py"],
                                "must": {"haveType": "file"},
                            }
                        ],
                    }
                ]
            ),
            file_system=FakeFileSystem(directories=["src/special.py"]),
        )

        assert result.diagnostics == []

    def test_block_level_exclude_files_with_for_skips_matching_child(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "for-exclude",
                        "paths": "components/{name}",
                        "must": [
                            {
                                "for": {"files": "*.py"},
                                "excludeFiles": ["helpers.py"],
                                "must": {"haveType": "directory"},
                            }
                        ],
                    }
                ]
            ),
            file_system=FakeFileSystem(
                files=[
                    "components/Button/Button.py",
                    "components/Button/helpers.py",
                ],
                directories=["components/Button"],
            ),
        )

        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].file_path == "components/Button/Button.py"

    def test_convention_and_block_exclude_files_coexist(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "coexist",
                        "paths": "src/*.py",
                        "excludeFiles": ["src/a.py"],
                        "must": [
                            {
                                "excludeFiles": ["src/b.py"],
                                "must": {"haveType": "file"},
                            }
                        ],
                    }
                ]
            ),
            file_system=FakeFileSystem(
                directories=["src/a.py", "src/b.py", "src/c.py"],
            ),
        )

        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].file_path == "src/c.py"


class TestSeverityAndNames:
    def test_defaults_to_error_severity(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "default-severity",
                        "paths": "src",
                        "must": {"haveType": "file"},
                    }
                ]
            ),
            file_system=FakeFileSystem(directories=["src"]),
        )

        assert result.diagnostics[0].severity == "error"

    def test_propagates_warning_severity(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "warnings",
                        "severity": "warning",
                        "paths": "src",
                        "must": {"haveType": "file"},
                    }
                ]
            ),
            file_system=FakeFileSystem(directories=["src"]),
        )

        assert result.diagnostics[0].severity == "warning"

    def test_uses_block_name_over_convention_name(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "convention-name",
                        "paths": "src",
                        "must": [
                            {
                                "name": "block-name",
                                "must": {"haveType": "file"},
                            }
                        ],
                    }
                ]
            ),
            file_system=FakeFileSystem(directories=["src"]),
        )

        assert result.diagnostics[0].convention_name == "block-name"

    def test_keeps_mixed_severities_from_multiple_conventions(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "errors",
                        "severity": "error",
                        "paths": "src",
                        "must": {"haveType": "file"},
                    },
                    {
                        "name": "warnings",
                        "severity": "warning",
                        "paths": "lib",
                        "must": {"haveType": "file"},
                    },
                ]
            ),
            file_system=FakeFileSystem(directories=["src", "lib"]),
        )

        assert sorted(diagnostic.severity for diagnostic in result.diagnostics) == [
            "error",
            "warning",
        ]


class TestMustNot:
    def test_object_level_must_not_emits_forbidden_diagnostic_when_positive_passes(
        self,
    ) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "not-files",
                        "paths": "src/index.py",
                        "mustNot": {"haveType": "file"},
                    }
                ]
            ),
            file_system=FakeFileSystem(files=["src/index.py"]),
        )

        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].predicate_name == "mustNot.haveType"
        assert result.diagnostics[0].message == 'Forbidden path type "file"'
        assert result.diagnostics[0].convention_name == "not-files"

    def test_object_level_must_not_emits_nothing_when_positive_fails(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "not-files",
                        "paths": "src",
                        "mustNot": {"haveType": "file"},
                    }
                ]
            ),
            file_system=FakeFileSystem(directories=["src"]),
        )

        assert result.diagnostics == []

    def test_item_level_must_not_splits_array_items(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "no-debug-files",
                        "paths": "plugins/auth",
                        "mustNot": {"haveFiles": ["debug.py", "missing.py"]},
                    }
                ]
            ),
            file_system=FakeFileSystem(
                files=["plugins/auth/debug.py"],
                directories=["plugins/auth"],
            ),
        )

        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].predicate_name == "mustNot.haveFiles"
        assert result.diagnostics[0].message == 'Forbidden file "debug.py"'

    def test_must_not_import_from_emits_forbidden_message(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "no-collections",
                        "paths": "src/module.py",
                        "mustNot": {"importFrom": "collections"},
                    }
                ]
            ),
            file_system=FakeFileSystem(
                contents={
                    "src/module.py": "from collections import deque\n",
                },
            ),
        )

        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].predicate_name == "mustNot.importFrom"
        assert result.diagnostics[0].message == 'Forbidden import from "collections"'

    def test_item_level_must_not_splits_ast_predicate_items(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "no-debug-constants",
                        "paths": "src/module.py",
                        "mustNot": {"exportConstants": ["DEBUG", "MISSING"]},
                    }
                ]
            ),
            file_system=FakeFileSystem(
                contents={"src/module.py": "DEBUG = True\n"},
            ),
        )

        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].predicate_name == "mustNot.exportConstants"
        assert result.diagnostics[0].message == 'Forbidden constant export "DEBUG"'

    def test_must_not_match_content_splits_regex_items(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "no-forbidden-content",
                        "paths": "src/service.py",
                        "mustNot": {"matchContent": ["TODO", "password\\s*="]},
                    }
                ]
            ),
            file_system=FakeFileSystem(
                contents={"src/service.py": "# TODO: clean up\nVALUE = 1\n"},
            ),
        )

        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].predicate_name == "mustNot.matchContent"
        assert result.diagnostics[0].message == 'Forbidden content matching regex "TODO"'

    def test_must_not_have_paired_file_emits_forbidden_message(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "no-paired-tests",
                        "paths": "src/{name}.py",
                        "mustNot": {"havePairedFile": "tests/test_${name}.py"},
                    }
                ]
            ),
            file_system=FakeFileSystem(
                contents={"src/service.py": "VALUE = 1\n"},
                files=["tests/test_service.py"],
            ),
        )

        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].predicate_name == "mustNot.havePairedFile"
        assert result.diagnostics[0].message == 'Forbidden paired file "tests/test_service.py"'

    def test_must_not_have_docstrings_emits_forbidden_message_when_coverage_passes(
        self,
    ) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "no-docstring-coverage",
                        "paths": "src/service.py",
                        "mustNot": {"haveDocstrings": True},
                    }
                ]
            ),
            file_system=FakeFileSystem(
                contents={
                    "src/service.py": (
                        '"""Module docs."""\n\n'
                        "class Service:\n"
                        '    """Service docs."""\n\n'
                        "    def run(self) -> None:\n"
                        '        """Run docs."""\n'
                        "        return None\n\n"
                        "def create() -> Service:\n"
                        '    """Create docs."""\n'
                        "    return Service()\n"
                    )
                },
            ),
        )

        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].predicate_name == "mustNot.haveDocstrings"
        assert result.diagnostics[0].message == "Forbidden docstring coverage"

    def test_must_not_annotate_functions_emits_forbidden_message_when_coverage_passes(
        self,
    ) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "no-annotation-coverage",
                        "paths": "src/service.py",
                        "mustNot": {"annotateFunctions": True},
                    }
                ]
            ),
            file_system=FakeFileSystem(
                contents={
                    "src/service.py": (
                        "class Service:\n"
                        "    def run(self, value: str) -> str:\n"
                        "        return value\n\n"
                        "def create(name: str) -> Service:\n"
                        "    return Service()\n"
                    )
                },
            ),
        )

        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].predicate_name == "mustNot.annotateFunctions"
        assert result.diagnostics[0].message == "Forbidden function annotation coverage"


class TestAstIntegration:
    def test_runs_ast_predicates_end_to_end(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "ast-rule",
                        "paths": "src/module.py",
                        "must": {
                            "export": ["public"],
                            "importFrom": "collections",
                            "areBarrelFiles": True,
                        },
                    }
                ]
            ),
            file_system=FakeFileSystem(
                contents={
                    "src/module.py": (
                        "from collections import deque\n\n"
                        "def public():\n"
                        "    pass\n"
                    )
                },
            ),
        )

        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].predicate_name == "areBarrelFiles"
        assert result.diagnostics[0].message == "Barrel file must not contain declarations"

    def test_ast_predicates_can_pass_without_diagnostics(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "barrel",
                        "paths": "src/__init__.py",
                        "must": {
                            "export": [{"name": "helper", "from": ".helper"}],
                            "importFrom": ".helper",
                            "areBarrelFiles": True,
                        },
                    }
                ]
            ),
            file_system=FakeFileSystem(
                contents={"src/__init__.py": "from .helper import helper\n"},
            ),
        )

        assert result.diagnostics == []


class TestCaching:
    def test_parses_same_file_only_once_across_multiple_conventions(self) -> None:
        file_system = CountingFileSystem(
            contents={"src/shared.py": "VALUE = 1\n"},
        )

        result = run(
            config=config(
                [
                    {
                        "name": "exports",
                        "paths": "src/shared.py",
                        "must": {"exportConstants": ["VALUE"]},
                    },
                    {
                        "name": "barrel",
                        "paths": "src/shared.py",
                        "must": {"areBarrelFiles": False},
                    },
                ]
            ),
            file_system=file_system,
        )

        assert result.diagnostics == []
        assert file_system.read_file_calls == ["src/shared.py"]

    def test_does_not_read_file_for_non_ast_predicates(self) -> None:
        """Suppression scanning reads checked source files even for non-AST rules."""
        file_system = CountingFileSystem(
            contents={"src/index.py": "VALUE = 1\n"},
        )

        result = run(
            config=config(
                [
                    {
                        "name": "type-only",
                        "paths": "src/index.py",
                        "must": {"haveType": "file"},
                    }
                ]
            ),
            file_system=file_system,
        )

        assert result.diagnostics == []
        assert file_system.read_file_calls == ["src/index.py"]



def plugin_config(
    conventions: list[dict],
    *,
    predicate_registry: PredicateRegistry,
    **extra: object,
) -> ConfigV1:
    return ConfigV1.model_validate(
        {
            "version": "v1",
            "plugins": ["konsistent-test-runner-plugin"],
            "conventions": conventions,
            **extra,
        },
        context=predicate_registry.validation_context(),
    )


def plugin_registry(
    *,
    key: str,
    value_model: Any,
    handler: PredicateHandler,
    forbidden_message: str | None = None,
    uses_ast: bool = False,
    item_level_must_not: bool = False,
) -> PredicateRegistry:
    base = builtin_predicate_registry()
    handlers = dict(base.handlers)
    handlers[key] = handler

    ast_predicates = set(base.ast_predicates)
    if uses_ast:
        ast_predicates.add(key)

    item_level_must_not_predicates = set(base.item_level_must_not_predicates)
    if item_level_must_not:
        item_level_must_not_predicates.add(key)

    def default_forbidden(value: Any, context: PredicateContext) -> str:
        del context
        return f'Forbidden {key} "{value}"'

    def templated_forbidden(value: Any, context: PredicateContext) -> str:
        resolved_value = context.resolve_template(value) if isinstance(value, str) else str(value)
        return str(forbidden_message).format(value=str(value), resolved_value=resolved_value)

    return PredicateRegistry(
        handlers=handlers,
        ast_predicates=frozenset(ast_predicates),
        item_level_must_not_predicates=frozenset(item_level_must_not_predicates),
        plugin_value_adapters={key: TypeAdapter(value_model)},
        plugin_forbidden_messages={
            key: templated_forbidden if forbidden_message is not None else default_forbidden
        },
        plugin_validate_placeholders={key: True},
        plugin_origins={},
    )


class TestPluginPredicates:
    def test_plugin_must_handler_emits_diagnostic(self) -> None:
        def handler(
            value: Any,
            context: PredicateContext,
            file_system: FileSystem,
            structure: PyFileStructure | None,
            convention_name: str | None,
            severity: DiagnosticSeverity | None,
        ) -> list[Diagnostic]:
            del structure
            source = file_system.read_file(context.path)
            if str(value) in source:
                return []
            return [
                create_diagnostic(
                    file_path=context.path,
                    predicate_name="requireMarker",
                    message=f'Missing marker "{value}"',
                    convention_name=convention_name,
                    severity=severity,
                )
            ]

        registry = plugin_registry(
            key="requireMarker",
            value_model=str,
            handler=handler,
        )

        result = run(
            config=plugin_config(
                [
                    {
                        "name": "plugin-marker",
                        "paths": "src/module.py",
                        "must": {"requireMarker": "PLUGIN_OK"},
                    }
                ],
                predicate_registry=registry,
            ),
            file_system=FakeFileSystem(contents={"src/module.py": "VALUE = 1\n"}),
            predicate_registry=registry,
        )

        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].predicate_name == "requireMarker"
        assert result.diagnostics[0].message == 'Missing marker "PLUGIN_OK"'
        assert result.diagnostics[0].convention_name == "plugin-marker"

    def test_plugin_must_handler_can_pass_cleanly(self) -> None:
        def handler(
            value: Any,
            context: PredicateContext,
            file_system: FileSystem,
            structure: PyFileStructure | None,
            convention_name: str | None,
            severity: DiagnosticSeverity | None,
        ) -> list[Diagnostic]:
            del structure, convention_name, severity
            source = file_system.read_file(context.path)
            if str(value) in source:
                return []
            return [
                create_diagnostic(
                    file_path=context.path,
                    predicate_name="requireMarker",
                    message=f'Missing marker "{value}"',
                )
            ]

        registry = plugin_registry(
            key="requireMarker",
            value_model=str,
            handler=handler,
        )

        result = run(
            config=plugin_config(
                [
                    {
                        "name": "plugin-marker",
                        "paths": "src/module.py",
                        "must": {"requireMarker": "PLUGIN_OK"},
                    }
                ],
                predicate_registry=registry,
            ),
            file_system=FakeFileSystem(contents={"src/module.py": "# PLUGIN_OK\n"}),
            predicate_registry=registry,
        )

        assert result.diagnostics == []

    def test_plugin_must_not_uses_plugin_forbidden_message(self) -> None:
        def handler(
            value: Any,
            context: PredicateContext,
            file_system: FileSystem,
            structure: PyFileStructure | None,
            convention_name: str | None,
            severity: DiagnosticSeverity | None,
        ) -> list[Diagnostic]:
            del structure, convention_name, severity
            source = file_system.read_file(context.path)
            if str(value) in source:
                return []
            return [
                create_diagnostic(
                    file_path=context.path,
                    predicate_name="requireMarker",
                    message=f'Missing marker "{value}"',
                )
            ]

        registry = plugin_registry(
            key="requireMarker",
            value_model=str,
            handler=handler,
            forbidden_message='Forbidden marker "{resolved_value}"',
        )

        result = run(
            config=plugin_config(
                [
                    {
                        "name": "no-plugin-marker",
                        "paths": "src/module.py",
                        "mustNot": {"requireMarker": "PLUGIN_OK"},
                    }
                ],
                predicate_registry=registry,
            ),
            file_system=FakeFileSystem(contents={"src/module.py": "# PLUGIN_OK\n"}),
            predicate_registry=registry,
        )

        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].predicate_name == "mustNot.requireMarker"
        assert result.diagnostics[0].message == 'Forbidden marker "PLUGIN_OK"'

    def test_plugin_item_level_must_not_splits_list_values(self) -> None:
        def handler(
            value: Any,
            context: PredicateContext,
            file_system: FileSystem,
            structure: PyFileStructure | None,
            convention_name: str | None,
            severity: DiagnosticSeverity | None,
        ) -> list[Diagnostic]:
            del structure, convention_name, severity
            source = file_system.read_file(context.path)
            missing = [marker for marker in value if marker not in source]
            return [
                create_diagnostic(
                    file_path=context.path,
                    predicate_name="requireMarkers",
                    message=f'Missing marker "{marker}"',
                )
                for marker in missing
            ]

        registry = plugin_registry(
            key="requireMarkers",
            value_model=list[str],
            handler=handler,
            forbidden_message='Forbidden marker "{value}"',
            item_level_must_not=True,
        )

        result = run(
            config=plugin_config(
                [
                    {
                        "name": "no-debug-markers",
                        "paths": "src/module.py",
                        "mustNot": {"requireMarkers": ["DEBUG", "MISSING"]},
                    }
                ],
                predicate_registry=registry,
            ),
            file_system=FakeFileSystem(contents={"src/module.py": "# DEBUG\n"}),
            predicate_registry=registry,
        )

        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].predicate_name == "mustNot.requireMarkers"
        assert result.diagnostics[0].message == 'Forbidden marker "DEBUG"'

    def test_plugin_uses_ast_receives_structure(self) -> None:
        def handler(
            value: Any,
            context: PredicateContext,
            file_system: FileSystem,
            structure: PyFileStructure | None,
            convention_name: str | None,
            severity: DiagnosticSeverity | None,
        ) -> list[Diagnostic]:
            del file_system
            if structure is None:
                return [
                    create_diagnostic(
                        file_path=context.path,
                        predicate_name="declarePluginFunction",
                        message="Plugin handler did not receive AST structure",
                        convention_name=convention_name,
                        severity=severity,
                    )
                ]

            names = {function.name for function in structure.functions}
            if str(value) in names:
                return []

            return [
                create_diagnostic(
                    file_path=context.path,
                    predicate_name="declarePluginFunction",
                    message=f'Missing plugin function "{value}"',
                    convention_name=convention_name,
                    severity=severity,
                )
            ]

        registry = plugin_registry(
            key="declarePluginFunction",
            value_model=str,
            handler=handler,
            uses_ast=True,
        )

        result = run(
            config=plugin_config(
                [
                    {
                        "name": "plugin-ast",
                        "paths": "src/module.py",
                        "must": {"declarePluginFunction": "run"},
                    }
                ],
                predicate_registry=registry,
            ),
            file_system=FakeFileSystem(contents={"src/module.py": "def run():\n    pass\n"}),
            predicate_registry=registry,
        )

        assert result.diagnostics == []


class TestRuntimeSuppressions:
    def test_suppresses_must_diagnostics_by_convention_name(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "annotations",
                        "paths": "src/service.py",
                        "must": {"annotateFunctions": True},
                    }
                ]
            ),
            file_system=FakeFileSystem(
                contents={
                    "src/service.py": (
                        "# konsistent: ignore[annotations] -- legacy API\n"
                        "def create(value):\n"
                        "    return value\n"
                    )
                },
            ),
        )

        assert result.diagnostics == []
        assert len(result.suppressed_diagnostics) == 2
        assert {item.diagnostic.predicate_name for item in result.suppressed_diagnostics} == {
            "annotateFunctions"
        }
        assert result.suppressed_diagnostics[0].suppression.reason == "legacy API"

    def test_suppresses_must_not_diagnostics_by_convention_name(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "no-paired-tests",
                        "paths": "src/service.py",
                        "mustNot": {"havePairedFile": "tests/test_service.py"},
                    }
                ]
            ),
            file_system=FakeFileSystem(
                contents={
                    "src/service.py": (
                        "# konsistent: ignore-file[no-paired-tests] -- generated\n"
                        "VALUE = 1\n"
                    )
                },
                files=["tests/test_service.py"],
            ),
        )

        assert result.diagnostics == []
        assert len(result.suppressed_diagnostics) == 1
        assert result.suppressed_diagnostics[0].diagnostic.predicate_name == (
            "mustNot.havePairedFile"
        )
        assert result.suppressed_diagnostics[0].suppression.kind == "ignore-file"

    def test_does_not_suppress_by_predicate_name(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "annotations",
                        "paths": "src/service.py",
                        "must": {"annotateFunctions": True},
                    }
                ]
            ),
            file_system=FakeFileSystem(
                contents={
                    "src/service.py": (
                        "# konsistent: ignore[annotate-functions]\n"
                        "def create(value):\n"
                        "    return value\n"
                    )
                },
            ),
            report_suppression_warnings=False,
        )

        assert len(result.diagnostics) == 2
        assert result.suppressed_diagnostics == []

    def test_suppresses_plugin_diagnostic(self) -> None:
        def handler(
            value: Any,
            context: PredicateContext,
            file_system: FileSystem,
            structure: PyFileStructure | None,
            convention_name: str | None,
            severity: DiagnosticSeverity | None,
        ) -> list[Diagnostic]:
            del structure
            source = file_system.read_file(context.path)
            if str(value) in source:
                return []
            return [
                create_diagnostic(
                    file_path=context.path,
                    predicate_name="requireMarker",
                    message=f'Missing marker "{value}"',
                    convention_name=convention_name,
                    line=2,
                    severity=severity,
                )
            ]

        registry = plugin_registry(
            key="requireMarker",
            value_model=str,
            handler=handler,
        )

        result = run(
            config=plugin_config(
                [
                    {
                        "name": "plugin-marker",
                        "paths": "src/module.py",
                        "must": {"requireMarker": "PLUGIN_OK"},
                    }
                ],
                predicate_registry=registry,
            ),
            file_system=FakeFileSystem(
                contents={
                    "src/module.py": (
                        "# konsistent: ignore[plugin-marker] -- generated fixture\n"
                        "VALUE = 1\n"
                    )
                },
            ),
            predicate_registry=registry,
        )

        assert result.diagnostics == []
        assert len(result.suppressed_diagnostics) == 1
        assert result.suppressed_diagnostics[0].diagnostic.predicate_name == "requireMarker"

    def test_suppresses_unused_code_diagnostics_after_unused_engine_runs(self) -> None:
        result = run(
            config=config([], unusedCode={}),
            file_system=FakeFileSystem(
                contents={
                    "src/service.py": (
                        "# konsistent: ignore[unused-code] -- public API\n"
                        "def orphaned():\n"
                        "    return 1\n"
                    )
                },
            ),
        )

        assert result.diagnostics == []
        assert len(result.suppressed_diagnostics) == 1
        assert result.suppressed_diagnostics[0].diagnostic.convention_name == "unused-code"
        assert result.suppressed_diagnostics[0].diagnostic.severity == "warning"

    def test_reports_unused_suppression_hygiene_warning(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "source-files",
                        "paths": "src/index.py",
                        "must": {"haveType": "file"},
                    }
                ]
            ),
            file_system=FakeFileSystem(
                contents={
                    "src/index.py": "# konsistent: ignore[source-files]\nVALUE = 1\n"
                },
            ),
        )

        assert result.suppressed_diagnostics == []
        assert [item.message for item in result.diagnostics] == [
            'Unused suppression for "source-files"'
        ]
        assert result.diagnostics[0].severity == "warning"
        assert result.diagnostics[0].convention_name == "suppressions"

    def test_reports_unknown_suppression_hygiene_warning(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "source-files",
                        "paths": "src/index.py",
                        "must": {"haveType": "file"},
                    }
                ]
            ),
            file_system=FakeFileSystem(
                contents={
                    "src/index.py": "# konsistent: ignore[not-a-rule]\nVALUE = 1\n"
                },
            ),
        )

        assert [item.message for item in result.diagnostics] == [
            'Unknown suppression rule "not-a-rule"'
        ]

    def test_report_suppression_warnings_false_omits_hygiene_warnings(self) -> None:
        result = run(
            config=config(
                [
                    {
                        "name": "source-files",
                        "paths": "src/index.py",
                        "must": {"haveType": "file"},
                    }
                ]
            ),
            file_system=FakeFileSystem(
                contents={
                    "src/index.py": "# konsistent: ignore[source-files]\nVALUE = 1\n"
                },
            ),
            report_suppression_warnings=False,
        )

        assert result.diagnostics == []
        assert result.suppressed_diagnostics == []

    def test_source_cache_reads_ast_file_once_for_predicates_and_suppression_scan(
        self,
    ) -> None:
        file_system = CountingFileSystem(
            contents={"src/shared.py": "# konsistent: ignore[exports]\nVALUE = 1\n"},
        )

        result = run(
            config=config(
                [
                    {
                        "name": "exports",
                        "paths": "src/shared.py",
                        "must": {"exportConstants": ["VALUE"]},
                    }
                ]
            ),
            file_system=file_system,
            report_suppression_warnings=False,
        )

        assert result.diagnostics == []
        assert file_system.read_file_calls == ["src/shared.py"]
