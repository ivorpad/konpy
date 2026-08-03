"""Tests for `konpy.core._report_duplication` (cross-component detection, ranking)."""

from __future__ import annotations

# `konpy.config` must finish importing before anything under
# `konpy.predicates` does: `konpy.predicates.registry` and
# `konpy.config.plugin_loader` import each other, and hitting predicates
# first breaks on a partially-initialized `konpy.predicates.registry`. Every
# real `konpy` entry point happens to import `konpy.config` first already;
# this test module is the first to reach `konpy.predicates` directly, so it
# has to establish that order itself.
import konpy.config  # noqa: F401
from konpy.core._report_duplication import _component, _duplication, _function_group, _group_label
from konpy.predicates._duplication_index import (
    _DuplicateFunctionGroup,
    _FunctionFingerprintOccurrence,
)
from konpy.python_ast import parse_file_structure
from konpy.python_ast.structure import SourcePosition

_SUM_POSITIVE = (
    "def {name}(values: list[int]) -> int:\n"
    "    total = 0\n"
    "    for value in values:\n"
    "        if value > 0:\n"
    "            total += value\n"
    "    return total\n"
)

_SUM_NEGATIVE = (
    "def {name}(values: list[int]) -> int:\n"
    "    total = 1\n"
    "    for value in values:\n"
    "        if value < 0:\n"
    "            total -= value\n"
    "    return total\n"
)


def _occurrence(
    file_path: str, *, name: str = "f", statement_count: int = 4
) -> _FunctionFingerprintOccurrence:
    return _FunctionFingerprintOccurrence(
        file_path=file_path,
        name=name,
        qualified_name=name,
        is_public=True,
        pos=SourcePosition(line=1, column=0),
        fingerprint="fp",
        statement_count=statement_count,
    )


class TestComponent:
    def test_flat_layout_uses_first_segment(self) -> None:
        assert _component("pkg_a/mod.py") == "pkg_a"
        assert _component("pkg_b/sub/mod.py") == "pkg_b"

    def test_src_layout_uses_second_segment(self) -> None:
        assert _component("src/pkg_a/mod.py") == "pkg_a"
        assert _component("src/pkg_b/sub/mod.py") == "pkg_b"

    def test_lib_layout_uses_second_segment(self) -> None:
        assert _component("lib/pkg_a/mod.py") == "pkg_a"

    def test_root_level_file_is_its_own_component(self) -> None:
        assert _component("mod.py") == "mod.py"

    def test_bare_src_root_file_falls_back_to_filename(self) -> None:
        # No package directory beneath src/ -- the file itself is the unit.
        assert _component("src/mod.py") == "mod.py"


class TestFunctionGroupCrossComponent:
    def test_same_component_is_not_cross_component(self) -> None:
        group = _DuplicateFunctionGroup(
            canonical=_occurrence("src/pkg_a/a.py"),
            duplicates=(_occurrence("src/pkg_a/b.py"),),
        )

        assert _function_group(group, generated=set()).is_cross_component is False

    def test_different_src_packages_is_cross_component(self) -> None:
        group = _DuplicateFunctionGroup(
            canonical=_occurrence("src/pkg_a/a.py"),
            duplicates=(_occurrence("src/pkg_b/b.py"),),
        )

        assert _function_group(group, generated=set()).is_cross_component is True

    def test_flat_layout_different_top_dirs_is_cross_component(self) -> None:
        group = _DuplicateFunctionGroup(
            canonical=_occurrence("service_a/a.py"),
            duplicates=(_occurrence("service_b/b.py"),),
        )

        assert _function_group(group, generated=set()).is_cross_component is True

    def test_flat_layout_same_top_dir_is_not_cross_component(self) -> None:
        group = _DuplicateFunctionGroup(
            canonical=_occurrence("service_a/a.py"),
            duplicates=(_occurrence("service_a/nested/b.py"),),
        )

        assert _function_group(group, generated=set()).is_cross_component is False


class TestFunctionGroupRanking:
    def test_cross_component_group_leads_even_with_lower_weight(self) -> None:
        # pkg_a's group has 3 members (weight 3x statements) all in one
        # component; pkg_x/pkg_y's group has only 2 members (weight 2x
        # statements) but spans two components. Cross-component must still
        # lead: blast radius, not raw size, is the primary sort key.
        structures = {
            "src/pkg_a/a.py": parse_file_structure(
                _SUM_POSITIVE.format(name="fn_a1"), "src/pkg_a/a.py"
            ),
            "src/pkg_a/b.py": parse_file_structure(
                _SUM_POSITIVE.format(name="fn_a2"), "src/pkg_a/b.py"
            ),
            "src/pkg_a/c.py": parse_file_structure(
                _SUM_POSITIVE.format(name="fn_a3"), "src/pkg_a/c.py"
            ),
            "src/pkg_x/one.py": parse_file_structure(
                _SUM_NEGATIVE.format(name="fn_x"), "src/pkg_x/one.py"
            ),
            "src/pkg_y/two.py": parse_file_structure(
                _SUM_NEGATIVE.format(name="fn_y"), "src/pkg_y/two.py"
            ),
        }

        _, function_groups = _duplication(structures, test_paths=set(), generated=set())

        assert len(function_groups) == 2
        assert function_groups[0].is_cross_component is True
        assert len(function_groups[0].members) == 2
        assert function_groups[1].is_cross_component is False
        assert len(function_groups[1].members) == 3


class TestGroupLabelTemplateAndVendored:
    def test_group_confined_to_template_paths_is_labeled_generator_template(self) -> None:
        template = frozenset({"tpl/{{cookiecutter.name}}/a.py", "tpl/{{cookiecutter.name}}/b.py"})

        label = _group_label(set(template), generated=set(), template=template)

        assert label == "generator template"

    def test_group_confined_to_vendored_paths_is_labeled_vendored(self) -> None:
        vendored = frozenset({"vendor/a.py", "vendor/b.py"})

        label = _group_label(set(vendored), generated=set(), vendored=vendored)

        assert label == "vendored"

    def test_group_spanning_template_and_production_code_is_not_labeled(self) -> None:
        template = frozenset({"tpl/{{cookiecutter.name}}/a.py"})
        paths = {"tpl/{{cookiecutter.name}}/a.py", "src/b.py"}

        label = _group_label(paths, generated=set(), template=template)

        assert label is None

    def test_generated_banner_takes_precedence_over_template(self) -> None:
        # A generated file inside a cookiecutter tree renders as generator
        # output either way -- the two rules agree on the same label, so
        # precedence between them is not user-visible, but generated (a
        # stronger, content-based signal) is checked first.
        paths = {"tpl/{{cookiecutter.name}}/a.py"}

        label = _group_label(paths, generated=set(paths), template=frozenset(paths))

        assert label == "generator template"

    def test_function_group_threads_template_and_vendored_into_the_label(self) -> None:
        group = _DuplicateFunctionGroup(
            canonical=_occurrence("vendor/a.py"),
            duplicates=(_occurrence("vendor/b.py"),),
        )

        report_group = _function_group(
            group, generated=set(), vendored=frozenset({"vendor/a.py", "vendor/b.py"})
        )

        assert report_group.label == "vendored"
