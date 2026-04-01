"""utils_core - Core utilities for orbit."""

from .paths import get_orbit_home, get_state_dir, get_package_root, codex_agents_dir, ensure_dir
from .safe_json import safe_json_parse, safe_json_dump, safe_read_json_file
from .platform_command import run_platform_command, is_macos, is_linux, get_shell
from .agents_md import find_agents_md, read_agents_md, has_agents_md

__all__ = [
    "get_orbit_home",
    "get_state_dir",
    "get_package_root",
    "codex_agents_dir",
    "ensure_dir",
    "safe_json_parse",
    "safe_json_dump",
    "safe_read_json_file",
    "run_platform_command",
    "is_macos",
    "is_linux",
    "get_shell",
    "find_agents_md",
    "read_agents_md",
    "has_agents_md",
]
