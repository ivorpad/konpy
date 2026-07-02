from __future__ import annotations

import pytest

from konsistent.config.schema import ConfigV1
from konsistent.core.convention_name import generate_convention_name
from konsistent.core.explain import (
    build_explained_config,
    render_explain,
)
from konsistent.unused import resolve_config


def _config(**overrides: object) -> ConfigV1:
    payload: dict[str, object] = {"version": "v1", "conventions": []}
    payload.update(overrides)
    return ConfigV1.model_validate(payload)


class TestBuildExplainedConfig:
    def test_convention_with_explicit_name_and_description_renders_both(self) -> None:
        config = _config(
            conventions=[
                {
                    "name": "must-have-readme",
                    "description": "Every package needs docs.",
                    "paths": "packages/*",
                    "must": {"haveFiles": ["README.md"]},
                }
            ]
        )

        md = render_explain(config, format="md")

        assert "`must-have-readme`" in md
        assert "Every package needs docs." in md

    def test_convention_without_name_uses_generate_convention_name(self) -> None:
        config = _config(
            conventions=[
                {
                    "paths": "src/*.py",
                    "must": {"exportFunctions": ["create"]},
                }
            ]
        )

        expected_name = generate_convention_name(
            must=config.conventions[0].must,
            must_not=None,
        )

        explained = build_explained_config(config)

        assert explained.conventions[0].name == expected_name

    def test_default_severity_is_error_when_unset(self) -> None:
        config = _config(
            conventions=[{"paths": "src/*.py", "must": {"haveType": "file"}}]
        )

        md = render_explain(config, format="md")
        text = render_explain(config, format="text")

        assert "severity: `error`" in md
        assert "severity: error" in text

    def test_explicit_warning_severity_is_preserved(self) -> None:
        config = _config(
            conventions=[
                {
                    "paths": "src/*.py",
                    "severity": "warning",
                    "must": {"haveType": "file"},
                }
            ]
        )

        md = render_explain(config, format="md")

        assert "severity: `warning`" in md

    def test_exclude_files_rendered_when_present(self) -> None:
        config = _config(
            conventions=[
                {
                    "paths": "src/*.py",
                    "excludeFiles": ["src/__init__.py"],
                    "must": {"haveType": "file"},
                }
            ]
        )

        md = render_explain(config, format="md")

        assert "src/__init__.py" in md

    def test_exclude_files_omitted_when_absent(self) -> None:
        config = _config(
            conventions=[{"paths": "src/*.py", "must": {"haveType": "file"}}]
        )

        md = render_explain(config, format="md")

        assert "excludes:" not in md

    def test_scalar_string_paths_normalized_to_single_item_list(self) -> None:
        config = _config(
            conventions=[{"paths": "src/*.py", "must": {"haveType": "file"}}]
        )

        explained = build_explained_config(config)

        assert explained.conventions[0].paths == ["src/*.py"]

    def test_multiple_paths_all_rendered_in_order(self) -> None:
        config = _config(
            conventions=[
                {
                    "paths": ["src/a.py", "src/b.py"],
                    "must": {"haveType": "file"},
                }
            ]
        )

        md = render_explain(config, format="md")

        assert md.index("src/a.py") < md.index("src/b.py")

    def test_boolean_predicate_renders_lowercase_true_false_not_python_repr(self) -> None:
        config = _config(
            conventions=[
                {"paths": "src/*.py", "must": {"areBarrelFiles": True}}
            ]
        )

        md = render_explain(config, format="md")

        assert "true" in md
        assert "True" not in md

    def test_declare_functions_object_value_renders_field_map(self) -> None:
        config = _config(
            conventions=[
                {
                    "paths": "src/*.py",
                    "must": {
                        "declareFunctions": [
                            {"name": "create", "receiveParamsOfTypes": ["Config"]}
                        ]
                    },
                }
            ]
        )

        md = render_explain(config, format="md")

        assert "name=create" in md
        assert "receiveParamsOfTypes=Config" in md

    def test_have_docstrings_true_literal_renders_true(self) -> None:
        config = _config(
            conventions=[{"paths": "src/*.py", "must": {"haveDocstrings": True}}]
        )

        md = render_explain(config, format="md")

        assert "true" in md

    def test_have_docstrings_options_object_renders_field_map(self) -> None:
        config = _config(
            conventions=[
                {
                    "paths": "src/*.py",
                    "must": {
                        "haveDocstrings": {"modules": True, "functions": False}
                    },
                }
            ]
        )

        md = render_explain(config, format="md")

        assert "modules=true" in md
        assert "functions=false" in md
        assert md.index("modules=true") < md.index("functions=false")

    def test_must_not_predicates_rendered_under_must_not_label(self) -> None:
        config = _config(
            conventions=[
                {"paths": "src/*.py", "mustNot": {"import": ["requests"]}}
            ]
        )

        md = render_explain(config, format="md")

        assert "must not:" in md
        assert "must:" not in md

    def test_single_anonymous_must_block_has_no_block_label(self) -> None:
        config = _config(
            conventions=[{"paths": "src/*.py", "must": {"haveType": "file"}}]
        )

        md = render_explain(config, format="md")

        assert "block 1" not in md
        assert "(block" not in md

    @pytest.mark.parametrize("named_first", [True, False])
    def test_multiple_must_blocks_each_labelled_by_index_when_unnamed(
        self, named_first: bool
    ) -> None:
        first_block: dict[str, object] = {"must": {"haveType": "file"}}
        second_block: dict[str, object] = {"mustNot": {"areBarrelFiles": True}}
        if named_first:
            first_block["name"] = "first-block"
        else:
            second_block["name"] = "second-block"

        config = _config(
            conventions=[
                {
                    "paths": "src/*.py",
                    "must": [first_block, second_block],
                }
            ]
        )

        md = render_explain(config, format="md")

        if named_first:
            assert "(first-block)" in md
            assert "(block 2)" in md
        else:
            assert "(block 1)" in md
            assert "(second-block)" in md

    def test_must_block_if_condition_rendered(self) -> None:
        config = _config(
            conventions=[
                {
                    "paths": "src/*.py",
                    "must": [
                        {
                            "if": {"hasFile": "pyproject.toml"},
                            "must": {"haveType": "file"},
                        }
                    ],
                }
            ]
        )

        md = render_explain(config, format="md")

        assert "hasFile" in md
        assert "`pyproject.toml`" in md

    def test_must_block_placeholder_satisfies_condition_rendered(self) -> None:
        config = _config(
            conventions=[
                {
                    "paths": "src/*.py",
                    "must": [
                        {
                            "if": {"placeholderSatisfies": "lang:python"},
                            "must": {"haveType": "file"},
                        }
                    ],
                }
            ]
        )

        md = render_explain(config, format="md")

        assert "placeholderSatisfies" in md
        assert "lang:python" in md

    def test_must_block_for_files_condition_rendered(self) -> None:
        config = _config(
            conventions=[
                {
                    "paths": "src/*.py",
                    "must": [
                        {
                            "for": {"files": ["*.py", "*.pyi"]},
                            "must": {"haveType": "file"},
                        }
                    ],
                }
            ]
        )

        md = render_explain(config, format="md")

        assert "*.py" in md
        assert "*.pyi" in md

    def test_must_block_exclude_files_rendered_as_condition_suffix(self) -> None:
        config = _config(
            conventions=[
                {
                    "paths": "src/*.py",
                    "must": [
                        {
                            "excludeFiles": ["src/__init__.py"],
                            "must": {"haveType": "file"},
                        }
                    ],
                }
            ]
        )

        md = render_explain(config, format="md")

        assert "except files matching" in md
        assert "src/__init__.py" in md

    def test_convention_with_must_list_and_top_level_must_not_appends_synthetic_block(
        self,
    ) -> None:
        config = _config(
            conventions=[
                {
                    "paths": "src/*.py",
                    "must": [{"must": {"haveType": "file"}}],
                    "mustNot": {"areBarrelFiles": True},
                }
            ]
        )

        md = render_explain(config, format="md")

        assert "must not" in md
        assert "areBarrelFiles" in md

    def test_convention_with_empty_must_list_and_no_must_not_renders_header_only(
        self,
    ) -> None:
        config = _config(
            conventions=[{"paths": "src/*.py", "must": []}]
        )

        md = render_explain(config, format="md")

        assert "must:" not in md
        assert "must not:" not in md

    def test_unused_code_absent_when_config_has_no_unusedCode_key(self) -> None:
        config = _config(conventions=[])

        md = render_explain(config, format="md")

        assert "Unused code" not in md

    def test_unused_code_section_present_with_resolved_engine_defaults(self) -> None:
        config = _config(conventions=[], unusedCode={})
        from konsistent.config.schema import UnusedCodeV1

        resolved = resolve_config(UnusedCodeV1())

        md = render_explain(config, format="md")

        assert "Unused code" in md
        for value in resolved.include:
            assert value in md
        for value in resolved.test_globs:
            assert value in md
        for value in resolved.entrypoint_files:
            assert value in md
        for value in resolved.registry_decorators:
            assert value in md
        for value in resolved.hook_names:
            assert value in md
        for value in resolved.model_bases:
            assert value in md

    def test_unused_code_allow_list_rendered_and_sorted(self) -> None:
        config = _config(
            conventions=[],
            unusedCode={"allow": ["zzz_legacy", "aaa_legacy"]},
        )

        md = render_explain(config, format="md")

        assert md.index("aaa_legacy") < md.index("zzz_legacy")

    def test_unused_code_hook_names_and_model_bases_rendered_sorted(self) -> None:
        config = _config(
            conventions=[],
            unusedCode={
                "hookNames": ["zzz_hook", "aaa_hook"],
                "modelBases": ["zzz_base", "aaa_base"],
            },
        )

        md = render_explain(config, format="md")

        assert md.index("aaa_hook") < md.index("zzz_hook")
        assert md.index("aaa_base") < md.index("zzz_base")

    def test_unused_code_empty_allow_list_renders_none_configured_placeholder(self) -> None:
        config = _config(conventions=[], unusedCode={})

        md = render_explain(config, format="md")

        assert "_(none configured)_" in md

    def test_no_conventions_renders_placeholder_text(self) -> None:
        config = _config(conventions=[])

        md = render_explain(config, format="md")
        text = render_explain(config, format="text")

        assert "_No conventions configured._" in md
        assert "(none configured)" in text

    def test_render_explain_is_deterministic_across_repeated_calls(self) -> None:
        config = _config(
            conventions=[{"paths": "src/*.py", "must": {"haveType": "file"}}],
            unusedCode={"allow": ["b", "a"]},
        )

        first = render_explain(config, format="md")
        second = render_explain(config, format="md")

        assert first == second

    def test_render_explain_text_format_has_no_markdown_syntax(self) -> None:
        config = _config(
            conventions=[
                {
                    "name": "example",
                    "description": "desc",
                    "paths": "src/*.py",
                    "must": {"haveType": "file"},
                }
            ],
        )

        text = render_explain(config, format="text")

        assert "`" not in text
        assert "**" not in text
        assert not any(line.startswith("#") for line in text.splitlines())

    def test_unknown_format_literal_raises(self) -> None:
        config = _config(conventions=[])

        with pytest.raises(ValueError, match="Unknown explain format"):
            render_explain(config, format="bogus")  # type: ignore[arg-type]
