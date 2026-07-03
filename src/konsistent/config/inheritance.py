from __future__ import annotations

from konsistent.config._config_resolution import resolve_config_inheritance
from konsistent.config._plugin_collection import collect_config_plugins

__all__ = ["collect_config_plugins", "resolve_config_inheritance"]
