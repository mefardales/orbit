"""Package root resolution."""
from __future__ import annotations
from pathlib import Path

def get_package_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent
