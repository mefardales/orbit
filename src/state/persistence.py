"""State persistence: save, load, and migrate application state to/from disk."""

from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

STATE_FILENAME = "state.json"
STATE_VERSION_KEY = "__version__"
CURRENT_VERSION = 3


def save_state(
    state: Dict[str, Any],
    directory: Path,
    filename: str = STATE_FILENAME,
    backup: bool = True,
) -> Path:
    """Save state dictionary to a JSON file.

    Creates a backup of the previous state file before writing.
    """
    directory.mkdir(parents=True, exist_ok=True)
    filepath = directory / filename

    if backup and filepath.exists():
        backup_path = directory / f"{filename}.bak"
        shutil.copy2(filepath, backup_path)
        logger.debug("Backed up state to %s", backup_path)

    data = dict(state)
    data[STATE_VERSION_KEY] = data.get(STATE_VERSION_KEY, CURRENT_VERSION)
    data["__saved_at__"] = time.time()

    tmp_path = filepath.with_suffix(".tmp")
    try:
        tmp_path.write_text(json.dumps(data, indent=2, default=str))
        tmp_path.replace(filepath)
    except OSError as e:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(f"Failed to save state: {e}") from e

    logger.info("Saved state to %s (%d keys)", filepath, len(state))
    return filepath


def load_state(
    directory: Path,
    filename: str = STATE_FILENAME,
    auto_migrate: bool = True,
) -> Dict[str, Any]:
    """Load state dictionary from a JSON file.

    Automatically migrates old versions if auto_migrate is True.
    """
    filepath = directory / filename

    if not filepath.exists():
        logger.info("No state file found at %s, returning empty state", filepath)
        return {STATE_VERSION_KEY: CURRENT_VERSION}

    try:
        data = json.loads(filepath.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Failed to load state from %s: %s", filepath, e)
        # Try backup
        backup_path = directory / f"{filename}.bak"
        if backup_path.exists():
            logger.info("Attempting to load backup state")
            try:
                data = json.loads(backup_path.read_text())
            except (json.JSONDecodeError, OSError):
                return {STATE_VERSION_KEY: CURRENT_VERSION}
        else:
            return {STATE_VERSION_KEY: CURRENT_VERSION}

    if auto_migrate:
        version = data.get(STATE_VERSION_KEY, 1)
        if version < CURRENT_VERSION:
            data = migrate_state(data, version, CURRENT_VERSION)
            save_state(data, directory, filename)

    return data


def migrate_state(
    state: Dict[str, Any],
    from_version: int,
    to_version: int,
) -> Dict[str, Any]:
    """Apply sequential migrations to bring state from one version to another."""
    data = dict(state)
    current = from_version

    migrations = {
        (1, 2): _migrate_v1_to_v2,
        (2, 3): _migrate_v2_to_v3,
    }

    while current < to_version:
        key = (current, current + 1)
        migrator = migrations.get(key)
        if migrator is None:
            logger.warning("No migration path from v%d to v%d", current, current + 1)
            break
        logger.info("Migrating state v%d -> v%d", current, current + 1)
        data = migrator(data)
        current += 1

    data[STATE_VERSION_KEY] = current
    return data


def _migrate_v1_to_v2(state: Dict[str, Any]) -> Dict[str, Any]:
    """Migration v1 -> v2: Flatten nested config, rename keys."""
    data = dict(state)

    # v1 had "config.model" nested; v2 uses flat keys
    if "config" in data and isinstance(data["config"], dict):
        config = data.pop("config")
        for k, v in config.items():
            data[f"config_{k}"] = v

    # Rename legacy keys
    renames = {
        "api_key": "auth_api_key",
        "model_name": "config_model",
        "max_tokens": "config_max_tokens",
    }
    for old_key, new_key in renames.items():
        if old_key in data and new_key not in data:
            data[new_key] = data.pop(old_key)

    data[STATE_VERSION_KEY] = 2
    return data


def _migrate_v2_to_v3(state: Dict[str, Any]) -> Dict[str, Any]:
    """Migration v2 -> v3: Add default settings, restructure history."""
    data = dict(state)

    # v3 adds a settings section with defaults
    if "settings" not in data:
        data["settings"] = {
            "theme": "default",
            "auto_save": True,
            "telemetry_enabled": False,
            "plugins_enabled": True,
        }

    # v3 restructures history from list to dict with metadata
    if "history" in data and isinstance(data["history"], list):
        entries = data.pop("history")
        data["history"] = {
            "entries": entries,
            "max_size": 100,
            "created_at": time.time(),
        }

    data[STATE_VERSION_KEY] = 3
    return data
