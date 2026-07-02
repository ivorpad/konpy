"""PlaceholderValue: a captured path-placeholder value plus its case
transformations. Port of core/placeholder.ts.

Custom case maps take precedence over the algorithmic conversion so that
acronyms like ``openai -> OpenAI`` survive round-trips. Empty-string map
values fall through to the algorithm (mirrors the JS truthiness check).
"""

import re

from konsistent.core.case_utils import (
    to_camel_case,
    to_constant_case,
    to_kebab_case,
    to_pascal_case,
    to_snake_case,
)


class PlaceholderValue:
    def __init__(
        self,
        value: str,
        *,
        kebab_to_pascal_map: dict[str, str] | None = None,
        kebab_to_camel_map: dict[str, str] | None = None,
        pascal_to_kebab_map: dict[str, str] | None = None,
        camel_to_kebab_map: dict[str, str] | None = None,
        camel_to_pascal_map: dict[str, str] | None = None,
        pascal_to_camel_map: dict[str, str] | None = None,
    ) -> None:
        self.raw = value
        self._kebab_to_pascal_map = kebab_to_pascal_map or {}
        self._kebab_to_camel_map = kebab_to_camel_map or {}
        self._pascal_to_kebab_map = pascal_to_kebab_map or {}
        self._camel_to_kebab_map = camel_to_kebab_map or {}
        self._camel_to_pascal_map = camel_to_pascal_map or {}
        self._pascal_to_camel_map = pascal_to_camel_map or {}

    def to_string(self) -> str:
        return self.raw

    def __str__(self) -> str:
        return self.raw

    def to_pascal_case(self) -> str:
        mapped = self._kebab_to_pascal_map.get(self.raw) or self._camel_to_pascal_map.get(self.raw)
        if mapped:
            return mapped
        return to_pascal_case(self.raw)

    def to_camel_case(self) -> str:
        mapped = self._kebab_to_camel_map.get(self.raw) or self._pascal_to_camel_map.get(self.raw)
        if mapped:
            return mapped
        pascal_mapped = self._kebab_to_pascal_map.get(self.raw)
        if pascal_mapped:
            return pascal_mapped[:1].lower() + pascal_mapped[1:]
        return to_camel_case(self.raw)

    def to_kebab_case(self) -> str:
        mapped = self._pascal_to_kebab_map.get(self.raw) or self._camel_to_kebab_map.get(self.raw)
        if mapped:
            return mapped
        return to_kebab_case(self.raw)

    def to_snake_case(self) -> str:
        mapped = self._pascal_to_kebab_map.get(self.raw) or self._camel_to_kebab_map.get(self.raw)
        if mapped:
            return mapped.replace("-", "_")
        return to_snake_case(self.raw)

    def to_constant_case(self) -> str:
        mapped = self._pascal_to_kebab_map.get(self.raw) or self._camel_to_kebab_map.get(self.raw)
        if mapped:
            return mapped.replace("-", "_").upper()
        return to_constant_case(self.raw)

    def to_flat_case(self) -> str:
        return re.sub(r"[^a-zA-Z0-9]", "", self.raw).lower()

    def to_nth_segment(self, n: int) -> str:
        segments = self.raw.split("-")
        return segments[n] if 0 <= n < len(segments) else ""

    def to_nth_segment_pascal_case(self, n: int) -> str:
        segment = self.to_nth_segment(n)
        if segment == "":
            return ""
        mapped = self._kebab_to_pascal_map.get(segment)
        if mapped:
            return mapped
        return segment[:1].upper() + segment[1:].lower()

    def to_nth_segment_camel_case(self, n: int) -> str:
        segment = self.to_nth_segment(n)
        if segment == "":
            return ""
        mapped = self._kebab_to_camel_map.get(segment)
        if mapped:
            return mapped
        pascal_mapped = self._kebab_to_pascal_map.get(segment)
        if pascal_mapped:
            return pascal_mapped[:1].lower() + pascal_mapped[1:]
        return segment.lower()

    def extract(self, pattern: str) -> str:
        try:
            regex = re.compile(pattern)
        except re.error:
            return ""
        match = regex.search(self.raw)
        if match is None:
            return ""
        if regex.groups > 0:
            return match.group(1) or ""
        return match.group(0)
