"""
Model Configuration

Reads per-mode model overrides and default-env overrides from .orbit-config.json.

Config format:
{
  "env": {
    "ORBIT_DEFAULT_FRONTIER_MODEL": "your-frontier-model",
    "ORBIT_DEFAULT_STANDARD_MODEL": "your-standard-model",
    "ORBIT_DEFAULT_SPARK_MODEL": "your-spark-model"
  },
  "models": {
    "default": "o4-mini",
    "team": "gpt-4.1"
  }
}

Resolution: mode-specific > "default" key > ORBIT_DEFAULT_FRONTIER_MODEL > DEFAULT_FRONTIER_MODEL
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from ..utils_core_mod import get_orbit_home as codex_home

ORBIT_DEFAULT_FRONTIER_MODEL_ENV = "ORBIT_DEFAULT_FRONTIER_MODEL"
ORBIT_DEFAULT_STANDARD_MODEL_ENV = "ORBIT_DEFAULT_STANDARD_MODEL"
ORBIT_DEFAULT_SPARK_MODEL_ENV = "ORBIT_DEFAULT_SPARK_MODEL"
ORBIT_SPARK_MODEL_ENV = "ORBIT_SPARK_MODEL"

DEFAULT_FRONTIER_MODEL = "gpt-5.4"
DEFAULT_STANDARD_MODEL = "gpt-5.4-mini"
DEFAULT_SPARK_MODEL = "gpt-5.3-codex-spark"

TEAM_LOW_COMPLEXITY_MODEL_KEYS = [
    "team_low_complexity",
    "team-low-complexity",
    "teamLowComplexity",
]


def _read_orbit_config_file(
    codex_home_override: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    config_path = Path(codex_home_override or codex_home()) / ".orbit-config.json"
    if not config_path.exists():
        return None
    try:
        raw = json.loads(config_path.read_text("utf-8"))
        if not isinstance(raw, dict):
            return None
        return raw
    except Exception:
        return None


def _read_models_block(
    codex_home_override: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    config = _read_orbit_config_file(codex_home_override)
    if not config:
        return None
    models = config.get("models")
    if isinstance(models, dict):
        return models
    return None


def _normalize_configured_value(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


def _read_config_env_value(
    key: str, codex_home_override: Optional[str] = None
) -> Optional[str]:
    config = _read_orbit_config_file(codex_home_override)
    if not config:
        return None
    env_block = config.get("env")
    if not isinstance(env_block, dict):
        return None
    return _normalize_configured_value(env_block.get(key))


def _read_team_low_complexity_override(
    codex_home_override: Optional[str] = None,
) -> Optional[str]:
    models = _read_models_block(codex_home_override)
    if not models:
        return None
    for key in TEAM_LOW_COMPLEXITY_MODEL_KEYS:
        value = _normalize_configured_value(models.get(key))
        if value:
            return value
    return None


def read_configured_env_overrides(
    codex_home_override: Optional[str] = None,
) -> dict[str, str]:
    """Read env overrides from .orbit-config.json."""
    config = _read_orbit_config_file(codex_home_override)
    if not config:
        return {}
    env_block = config.get("env")
    if not isinstance(env_block, dict):
        return {}
    resolved: dict[str, str] = {}
    for key, value in env_block.items():
        normalized = _normalize_configured_value(value)
        if normalized:
            resolved[key] = normalized
    return resolved


def get_env_configured_main_default_model(
    env: Optional[dict[str, str]] = None,
    codex_home_override: Optional[str] = None,
) -> Optional[str]:
    if env is None:
        env = dict(os.environ)
    return _normalize_configured_value(
        env.get(ORBIT_DEFAULT_FRONTIER_MODEL_ENV)
    ) or _read_config_env_value(ORBIT_DEFAULT_FRONTIER_MODEL_ENV, codex_home_override)


def get_env_configured_standard_default_model(
    env: Optional[dict[str, str]] = None,
    codex_home_override: Optional[str] = None,
) -> Optional[str]:
    if env is None:
        env = dict(os.environ)
    return _normalize_configured_value(
        env.get(ORBIT_DEFAULT_STANDARD_MODEL_ENV)
    ) or _read_config_env_value(ORBIT_DEFAULT_STANDARD_MODEL_ENV, codex_home_override)


def get_env_configured_spark_default_model(
    env: Optional[dict[str, str]] = None,
    codex_home_override: Optional[str] = None,
) -> Optional[str]:
    if env is None:
        env = dict(os.environ)
    return (
        _normalize_configured_value(env.get(ORBIT_DEFAULT_SPARK_MODEL_ENV))
        or _normalize_configured_value(env.get(ORBIT_SPARK_MODEL_ENV))
        or _read_config_env_value(ORBIT_DEFAULT_SPARK_MODEL_ENV, codex_home_override)
        or _read_config_env_value(ORBIT_SPARK_MODEL_ENV, codex_home_override)
    )


def get_main_default_model(codex_home_override: Optional[str] = None) -> str:
    """Get the envvar-backed main/default model.
    Resolution: ORBIT_DEFAULT_FRONTIER_MODEL > DEFAULT_FRONTIER_MODEL
    """
    return (
        get_env_configured_main_default_model(
            codex_home_override=codex_home_override
        )
        or DEFAULT_FRONTIER_MODEL
    )


def get_standard_default_model(codex_home_override: Optional[str] = None) -> str:
    """Get the envvar-backed standard/default subagent model.
    Resolution: ORBIT_DEFAULT_STANDARD_MODEL > DEFAULT_STANDARD_MODEL
    """
    return (
        get_env_configured_standard_default_model(
            codex_home_override=codex_home_override
        )
        or DEFAULT_STANDARD_MODEL
    )


def get_model_for_mode(mode: str, codex_home_override: Optional[str] = None) -> str:
    """Get the configured model for a specific mode.
    Resolution: mode-specific override > "default" key > ORBIT_DEFAULT_FRONTIER_MODEL > DEFAULT_FRONTIER_MODEL
    """
    models = _read_models_block(codex_home_override)
    if models:
        mode_value = _normalize_configured_value(models.get(mode))
        if mode_value:
            return mode_value
        default_value = _normalize_configured_value(models.get("default"))
        if default_value:
            return default_value
    return get_main_default_model(codex_home_override)


def get_spark_default_model(codex_home_override: Optional[str] = None) -> str:
    """Get the envvar-backed spark/low-complexity default model.
    Resolution: ORBIT_DEFAULT_SPARK_MODEL > ORBIT_SPARK_MODEL > explicit low-complexity key(s) > DEFAULT_SPARK_MODEL
    """
    return (
        get_env_configured_spark_default_model(
            codex_home_override=codex_home_override
        )
        or _read_team_low_complexity_override(codex_home_override)
        or DEFAULT_SPARK_MODEL
    )


def get_team_low_complexity_model(codex_home_override: Optional[str] = None) -> str:
    """Get the low-complexity team worker model.
    Resolution: explicit low-complexity key(s) > ORBIT_DEFAULT_SPARK_MODEL > ORBIT_SPARK_MODEL > DEFAULT_SPARK_MODEL
    """
    return _read_team_low_complexity_override(
        codex_home_override
    ) or get_spark_default_model(codex_home_override)
