import pytest
from pydantic import ValidationError

from konsistent.config.errors import Err, Ok, format_validation_error
from konsistent.config.schema import RawConfigV1


def validation_error_for(payload: dict) -> ValidationError:
    with pytest.raises(ValidationError) as exc_info:
        RawConfigV1.model_validate(payload)
    return exc_info.value


class TestResult:
    def test_ok(self) -> None:
        result = Ok(42)
        assert result.success is True
        assert result.value == 42

    def test_err(self) -> None:
        result = Err("boom")
        assert result.success is False
        assert result.error == "boom"


class TestFormatValidationError:
    def test_lines_are_indented_dashes(self) -> None:
        error = validation_error_for({"conventions": []})
        formatted = format_validation_error(error)
        assert formatted.startswith("  - ")

    def test_path_is_dotted_without_union_tags(self) -> None:
        error = validation_error_for(
            {
                "version": "v1",
                "conventions": [{"paths": "src/*.py", "must": {"haveType": "symlink"}}],
            }
        )
        formatted = format_validation_error(error)
        assert "conventions.0.must.haveType" in formatted

    def test_version_error_names_version_path(self) -> None:
        error = validation_error_for({"version": "v2", "conventions": []})
        formatted = format_validation_error(error)
        assert "version" in formatted.splitlines()[0]

    def test_keyword_aliases_render_as_json_keys(self) -> None:
        error = validation_error_for(
            {
                "version": "v1",
                "conventions": [
                    {
                        "paths": "src/*.py",
                        "must": [{"if": {"unknown": "x"}, "must": {"haveType": "file"}}],
                    }
                ],
            }
        )
        formatted = format_validation_error(error)
        assert ".if." in formatted or ".if:" in formatted
