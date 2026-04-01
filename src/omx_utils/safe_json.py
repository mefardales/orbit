"""Safe JSON parsing utilities."""
from __future__ import annotations
import json
from typing import Any

def safe_json_parse(text: str, default: Any = None) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default

def safe_json_dump(data: Any, indent: int = 2) -> str:
    try:
        return json.dumps(data, indent=indent, default=str)
    except (TypeError, ValueError):
        return '{}'
