from __future__ import annotations

from pathlib import Path

from konsistent.config.errors import Err, Ok
from konsistent.config.plugin_loader import load_plugin_registry
from tests.fake_distribution import install_fake_distribution


def plugin_source(*, key: str = "requireMarker", value_model: str = "str") -> str:
    return f'''
from konsistent.plugin import PredicatePlugin


def handler(*, expected, context, structure, convention_name=None, severity=None):
    return []


plugin = PredicatePlugin(
    key="{key}",
    value_model={value_model},
    handler=handler,
    forbidden_message_template='Forbidden marker "{{resolved_value}}"',
)
'''


def install_plugin(
    *,
    tmp_path: Path,
    monkeypatch,
    distribution_name: str,
    import_package: str,
    entry_point_name: str = "requireMarker",
    module_source: str | None = None,
) -> None:
    install_fake_distribution(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        distribution_name=distribution_name,
        import_package=import_package,
        modules={"rules": module_source or plugin_source()},
        entry_points={
            "konsistent.predicates": {
                entry_point_name: f"{import_package}.rules:plugin",
            }
        },
    )


class TestLoadPluginRegistry:
    def test_loads_descriptor_from_explicitly_listed_distribution(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_plugin(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konsistent-test-plugin",
            import_package="konsistent_test_plugin",
        )

        result = load_plugin_registry(plugins=["konsistent-test-plugin"])

        assert isinstance(result, Ok)
        assert "requireMarker" in result.value.handlers
        assert "requireMarker" in result.value.plugin_value_adapters
        assert result.value.plugin_validate_placeholders["requireMarker"] is True
        assert result.value.plugin_origins["requireMarker"].distribution_name == (
            "konsistent-test-plugin"
        )
        assert result.value.plugin_origins["requireMarker"].entry_point_name == "requireMarker"

    def test_accepts_zero_arg_callable_returning_descriptor(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        import_package = "konsistent_test_callable_plugin"
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konsistent-test-callable-plugin",
            import_package=import_package,
            modules={
                "rules": '''
from konsistent.plugin import PredicatePlugin


def handler(*, expected, context, structure, convention_name=None, severity=None):
    return []


def build_plugin():
    return PredicatePlugin(
        key="callableRule",
        value_model=str,
        handler=handler,
        forbidden_message_template="Forbidden callable rule",
    )
'''
            },
            entry_points={
                "konsistent.predicates": {
                    "callableRule": f"{import_package}.rules:build_plugin",
                }
            },
        )

        result = load_plugin_registry(plugins=["konsistent-test-callable-plugin"])

        assert isinstance(result, Ok)
        assert "callableRule" in result.value.handlers

    def test_does_not_auto_discover_installed_plugins(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_plugin(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konsistent-test-auto-plugin",
            import_package="konsistent_test_auto_plugin",
        )

        result = load_plugin_registry(plugins=[])

        assert isinstance(result, Ok)
        assert "requireMarker" not in result.value.handlers
        assert result.value.plugin_value_adapters == {}

    def test_rejects_invalid_distribution_name(self) -> None:
        result = load_plugin_registry(plugins=["@scope/plugin"])

        assert isinstance(result, Err)
        assert result.error == (
            'Plugin "@scope/plugin": invalid Python distribution name. Plugin names must '
            "match [A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9]."
        )

    def test_rejects_missing_distribution(self) -> None:
        result = load_plugin_registry(plugins=["konsistent-test-definitely-missing-plugin"])

        assert isinstance(result, Err)
        assert result.error == (
            'Plugin "konsistent-test-definitely-missing-plugin": installed Python '
            "distribution not found. Install it or remove it from plugins."
        )

    def test_rejects_distribution_without_predicate_entry_points(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konsistent-test-no-entry-points",
            import_package="konsistent_test_no_entry_points",
        )

        result = load_plugin_registry(plugins=["konsistent-test-no-entry-points"])

        assert isinstance(result, Err)
        assert result.error == (
            'Plugin "konsistent-test-no-entry-points": no entry points found in group '
            '"konsistent.predicates".'
        )

    def test_surfaces_entry_point_load_failures(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konsistent-test-broken-entry-point",
            import_package="konsistent_test_broken_entry_point",
            modules={"rules": "VALUE = 1\n"},
            entry_points={
                "konsistent.predicates": {
                    "brokenRule": "konsistent_test_broken_entry_point.rules:missing",
                }
            },
        )

        result = load_plugin_registry(plugins=["konsistent-test-broken-entry-point"])

        assert isinstance(result, Err)
        assert result.error.startswith(
            'Plugin "konsistent-test-broken-entry-point" entry point "brokenRule": '
            "failed to load:"
        )

    def test_rejects_entry_point_that_is_not_descriptor_or_factory(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konsistent-test-invalid-entry-point",
            import_package="konsistent_test_invalid_entry_point",
            modules={"rules": "plugin = object()\n"},
            entry_points={
                "konsistent.predicates": {
                    "invalidRule": "konsistent_test_invalid_entry_point.rules:plugin",
                }
            },
        )

        result = load_plugin_registry(plugins=["konsistent-test-invalid-entry-point"])

        assert isinstance(result, Err)
        assert result.error == (
            'Plugin "konsistent-test-invalid-entry-point" entry point "invalidRule" must '
            "load a PredicatePlugin instance or a zero-argument callable returning "
            "PredicatePlugin."
        )

    def test_rejects_callable_that_does_not_return_descriptor(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konsistent-test-invalid-factory",
            import_package="konsistent_test_invalid_factory",
            modules={"rules": "def build_plugin():\n    return object()\n"},
            entry_points={
                "konsistent.predicates": {
                    "invalidFactory": "konsistent_test_invalid_factory.rules:build_plugin",
                }
            },
        )

        result = load_plugin_registry(plugins=["konsistent-test-invalid-factory"])

        assert isinstance(result, Err)
        assert result.error == (
            'Plugin "konsistent-test-invalid-factory" entry point "invalidFactory" must '
            "load a PredicatePlugin instance or a zero-argument callable returning "
            "PredicatePlugin."
        )

    def test_rejects_invalid_descriptor_fields(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_plugin(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konsistent-test-invalid-descriptor",
            import_package="konsistent_test_invalid_descriptor",
            module_source=plugin_source(key=""),
        )

        result = load_plugin_registry(plugins=["konsistent-test-invalid-descriptor"])

        assert isinstance(result, Err)
        assert result.error == (
            'Plugin "konsistent-test-invalid-descriptor" entry point "requireMarker" '
            "declares an invalid predicate descriptor: key must be a non-empty string."
        )

    def test_rejects_invalid_value_model(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_plugin(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konsistent-test-invalid-value-model",
            import_package="konsistent_test_invalid_value_model",
            module_source=plugin_source(value_model="object()"),
        )

        result = load_plugin_registry(plugins=["konsistent-test-invalid-value-model"])

        assert isinstance(result, Err)
        assert (
            'Plugin "konsistent-test-invalid-value-model" entry point "requireMarker" '
            "declares an invalid predicate descriptor: value_model could not be adapted "
            "by pydantic:"
        ) in result.error

    def test_rejects_builtin_key_collision(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_plugin(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konsistent-test-builtin-collision",
            import_package="konsistent_test_builtin_collision",
            entry_point_name="haveType",
            module_source=plugin_source(key="haveType"),
        )

        result = load_plugin_registry(plugins=["konsistent-test-builtin-collision"])

        assert isinstance(result, Err)
        assert result.error == (
            'Plugin "konsistent-test-builtin-collision" entry point "haveType" declares '
            'predicate key "haveType", which conflicts with a built-in predicate. Choose '
            "a unique plugin predicate key."
        )

    def test_rejects_plugin_key_collision(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_plugin(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konsistent-test-plugin-a",
            import_package="konsistent_test_plugin_a",
            entry_point_name="firstRule",
            module_source=plugin_source(key="sameRule"),
        )
        install_plugin(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konsistent-test-plugin-b",
            import_package="konsistent_test_plugin_b",
            entry_point_name="secondRule",
            module_source=plugin_source(key="sameRule"),
        )

        result = load_plugin_registry(
            plugins=["konsistent-test-plugin-a", "konsistent-test-plugin-b"]
        )

        assert isinstance(result, Err)
        assert result.error == (
            'Plugin "konsistent-test-plugin-b" entry point "secondRule" declares predicate '
            'key "sameRule", which conflicts with plugin "konsistent-test-plugin-a" entry '
            'point "firstRule". Plugin predicate keys must be unique.'
        )

    def test_dedupes_repeated_plugin_names_by_normalized_distribution_name(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_plugin(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konsistent-test-repeat-plugin",
            import_package="konsistent_test_repeat_plugin",
        )

        result = load_plugin_registry(
            plugins=["konsistent-test-repeat-plugin", "konsistent_test_repeat_plugin"]
        )

        assert isinstance(result, Ok)
        assert "requireMarker" in result.value.handlers
