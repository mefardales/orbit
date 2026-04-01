"""Validation functions for configs, manifests, and agent definitions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class ValidationError:
    """A single validation error."""
    field: str
    message: str
    value: Any = None

    def __str__(self) -> str:
        return f"{self.field}: {self.message}"


@dataclass
class ValidationResult:
    """Result of a validation operation."""
    valid: bool
    errors: List[ValidationError] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.valid

    def add_error(self, field_name: str, message: str, value: Any = None) -> None:
        self.errors.append(ValidationError(field=field_name, message=message, value=value))
        self.valid = False

    @property
    def error_messages(self) -> List[str]:
        return [str(e) for e in self.errors]


def _check_type(result: ValidationResult, data: Dict, key: str, expected: type, required: bool = False) -> None:
    """Helper to check a field's type and required status."""
    if key not in data:
        if required:
            result.add_error(key, "required field is missing")
        return
    if not isinstance(data[key], expected):
        result.add_error(key, f"expected {expected.__name__}, got {type(data[key]).__name__}", data[key])


def _check_range(result: ValidationResult, data: Dict, key: str, min_val: Any = None, max_val: Any = None) -> None:
    """Helper to validate numeric range."""
    val = data.get(key)
    if val is None:
        return
    if min_val is not None and val < min_val:
        result.add_error(key, f"must be >= {min_val}", val)
    if max_val is not None and val > max_val:
        result.add_error(key, f"must be <= {max_val}", val)


VALID_MODELS = {
    "claude-sonnet-4-20250514",
    "claude-opus-4-20250514",
    "claude-haiku-3-20250307",
}

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def validate_config(data: Dict[str, Any]) -> ValidationResult:
    """Validate a orbit configuration dictionary."""
    result = ValidationResult(valid=True)

    if not isinstance(data, dict):
        result.add_error("root", "config must be a dictionary")
        return result

    # Model
    _check_type(result, data, "model", str)
    if "model" in data and data["model"] not in VALID_MODELS:
        result.add_error("model", f"unknown model; valid: {VALID_MODELS}", data["model"])

    # Token limits
    _check_type(result, data, "max_tokens", int)
    _check_range(result, data, "max_tokens", min_val=1, max_val=200_000)

    # Temperature
    _check_type(result, data, "temperature", (int, float))
    _check_range(result, data, "temperature", min_val=0.0, max_val=2.0)

    # Timeout
    _check_type(result, data, "timeout", (int, float))
    _check_range(result, data, "timeout", min_val=1, max_val=600)

    # Log level
    if "log_level" in data:
        if data["log_level"] not in VALID_LOG_LEVELS:
            result.add_error("log_level", f"must be one of {VALID_LOG_LEVELS}", data["log_level"])

    # Server
    if "server_port" in data:
        _check_type(result, data, "server_port", int)
        _check_range(result, data, "server_port", min_val=1, max_val=65535)

    if "server_host" in data:
        _check_type(result, data, "server_host", str)

    # API key
    if "api_key" in data:
        _check_type(result, data, "api_key", str)
        if isinstance(data["api_key"], str) and len(data["api_key"]) < 10:
            result.add_error("api_key", "API key appears too short")

    return result


SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(-[\w.]+)?$")


def validate_manifest(data: Dict[str, Any]) -> ValidationResult:
    """Validate a plugin manifest dictionary."""
    result = ValidationResult(valid=True)

    if not isinstance(data, dict):
        result.add_error("root", "manifest must be a dictionary")
        return result

    _check_type(result, data, "name", str, required=True)
    _check_type(result, data, "version", str, required=True)

    if "name" in data and isinstance(data["name"], str):
        if not re.match(r"^[a-z0-9_-]+$", data["name"]):
            result.add_error("name", "must be lowercase alphanumeric with hyphens/underscores")

    if "version" in data and isinstance(data["version"], str):
        if not SEMVER_RE.match(data["version"]):
            result.add_error("version", "must be valid semver (e.g., 1.0.0)")

    _check_type(result, data, "description", str)
    _check_type(result, data, "entry_point", str)
    _check_type(result, data, "dependencies", list)
    _check_type(result, data, "permissions", list)
    _check_type(result, data, "hooks", list)

    valid_perms = {"fs_read", "fs_write", "network", "process", "env"}
    if "permissions" in data and isinstance(data["permissions"], list):
        for perm in data["permissions"]:
            if perm not in valid_perms:
                result.add_error("permissions", f"unknown permission: {perm}", perm)

    return result


def validate_agent_def(data: Dict[str, Any]) -> ValidationResult:
    """Validate an agent definition dictionary."""
    result = ValidationResult(valid=True)

    if not isinstance(data, dict):
        result.add_error("root", "agent definition must be a dictionary")
        return result

    _check_type(result, data, "name", str, required=True)
    _check_type(result, data, "system_prompt", str, required=True)
    _check_type(result, data, "model", str)
    _check_type(result, data, "tools", list)
    _check_type(result, data, "max_turns", int)
    _check_range(result, data, "max_turns", min_val=1, max_val=100)
    _check_type(result, data, "temperature", (int, float))
    _check_range(result, data, "temperature", min_val=0.0, max_val=2.0)

    if "tools" in data and isinstance(data["tools"], list):
        for i, tool in enumerate(data["tools"]):
            if not isinstance(tool, dict):
                result.add_error(f"tools[{i}]", "each tool must be a dictionary")
            elif "name" not in tool:
                result.add_error(f"tools[{i}]", "tool must have a 'name' field")

    return result
