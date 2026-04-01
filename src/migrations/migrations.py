"""Concrete migration classes for orbit data schema evolution."""

from __future__ import annotations

import time
from typing import Any, Dict

from migrations.registry import BaseMigration, MigrationMeta


class MigrateV1ToV2(BaseMigration):
    """v1 -> v2: Flatten nested config, add auth section, rename legacy keys."""

    meta = MigrationMeta(
        from_version=1,
        to_version=2,
        name="MigrateV1ToV2",
        description="Flatten nested config and rename legacy keys",
        reversible=True,
    )

    def up(self, data: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(data)

        # Flatten nested "config" dict into top-level prefixed keys
        if "config" in result and isinstance(result["config"], dict):
            config = result.pop("config")
            for key, value in config.items():
                result[f"config_{key}"] = value

        # Rename legacy keys
        renames = {
            "api_key": "auth_api_key",
            "model_name": "config_model",
            "max_tokens": "config_max_tokens",
            "timeout": "config_timeout",
        }
        for old_key, new_key in renames.items():
            if old_key in result and new_key not in result:
                result[new_key] = result.pop(old_key)

        # Add auth section if missing
        if "auth" not in result:
            result["auth"] = {
                "method": "api_key",
                "token": result.get("auth_api_key", ""),
            }

        result["__version__"] = 2
        result["__migrated_at__"] = time.time()
        return result

    def down(self, data: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(data)

        # Unflatten config_ prefixed keys back into nested dict
        config = {}
        config_keys = [k for k in result if k.startswith("config_")]
        for key in config_keys:
            config[key[7:]] = result.pop(key)
        if config:
            result["config"] = config

        # Reverse key renames
        reverse_renames = {
            "auth_api_key": "api_key",
            "config_model": "model_name",
            "config_max_tokens": "max_tokens",
            "config_timeout": "timeout",
        }
        for old_key, new_key in reverse_renames.items():
            if old_key in result:
                result[new_key] = result.pop(old_key)

        result.pop("auth", None)
        result["__version__"] = 1
        return result

    def validate(self, data: Dict[str, Any]) -> bool:
        return data.get("__version__") == 2


class MigrateV2ToV3(BaseMigration):
    """v2 -> v3: Add settings section, restructure history, add plugin config."""

    meta = MigrationMeta(
        from_version=2,
        to_version=3,
        name="MigrateV2ToV3",
        description="Add settings, restructure history, add plugin config",
        reversible=True,
    )

    def up(self, data: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(data)

        # Add default settings section
        if "settings" not in result:
            result["settings"] = {
                "theme": "default",
                "auto_save": True,
                "telemetry_enabled": False,
                "plugins_enabled": True,
                "auto_update": False,
            }

        # Restructure flat history list into dict with metadata
        if "history" in result and isinstance(result["history"], list):
            entries = result["history"]
            result["history"] = {
                "entries": entries,
                "max_size": 100,
                "created_at": time.time(),
            }

        # Add plugin configuration
        if "plugins" not in result:
            result["plugins"] = {
                "enabled": True,
                "directories": [],
                "auto_load": True,
                "installed": {},
            }

        # Add state metadata
        if "meta" not in result:
            result["meta"] = {
                "created_at": time.time(),
                "schema_version": 3,
                "app_version": "0.1.0",
            }

        result["__version__"] = 3
        result["__migrated_at__"] = time.time()
        return result

    def down(self, data: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(data)

        # Flatten history back to list
        if "history" in result and isinstance(result["history"], dict):
            result["history"] = result["history"].get("entries", [])

        # Remove v3 sections
        result.pop("settings", None)
        result.pop("plugins", None)
        result.pop("meta", None)

        result["__version__"] = 2
        return result

    def validate(self, data: Dict[str, Any]) -> bool:
        if data.get("__version__") != 3:
            return False
        if "settings" not in data:
            return False
        return True
