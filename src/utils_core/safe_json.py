"""Safe JSON parsing and serialization utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union


def safe_json_parse(
    text: str,
    default: Optional[Any] = None,
    strict: bool = False,
) -> Any:
    """Parse a JSON string, returning a default value on failure.

    Args:
        text: The JSON string to parse.
        default: Value to return if parsing fails (default: None).
        strict: If True, raise on parse errors instead of returning default.
    """
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        if strict:
            raise
        return default


def safe_json_dump(
    data: Any,
    indent: int = 2,
    sort_keys: bool = False,
    default_serializer: Optional[Any] = None,
) -> str:
    """Serialize data to a JSON string, handling common edge cases.

    Args:
        data: The data to serialize.
        indent: Indentation level for pretty-printing.
        sort_keys: Whether to sort dictionary keys.
        default_serializer: Fallback serializer for non-standard types.
    """
    def _default(obj: Any) -> Any:
        if default_serializer:
            return default_serializer(obj)
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        return str(obj)

    try:
        return json.dumps(data, indent=indent, sort_keys=sort_keys, default=_default)
    except (TypeError, ValueError):
        return json.dumps(str(data))


def safe_read_json_file(
    path: Union[str, Path],
    default: Optional[Any] = None,
) -> Any:
    """Read and parse a JSON file, returning a default on any failure.

    Args:
        path: Path to the JSON file.
        default: Value to return if reading or parsing fails.
    """
    filepath = Path(path)
    if not filepath.exists():
        return default
    try:
        text = filepath.read_text(encoding="utf-8")
        return json.loads(text)
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return default
