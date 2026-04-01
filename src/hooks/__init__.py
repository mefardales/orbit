"""
Hooks module for orbit.

Provides keyword detection, session management, codebase mapping,
explore routing, AGENTS.md overlay injection, task size detection,
an extensibility framework for hook plugins, and an in-process hook
registry with plugin dispatch.
"""

from .plugin_loader import (
    load_plugins,
    validate_plugin,
    clear_plugin_cache,
)
from .dispatcher import (
    register_hook,
    unregister_hook,
    emit,
    dispatch,
    KNOWN_EVENTS,
    DispatchResult,
    PluginDispatchResult,
)
from .keyword_detector import (
    KeywordMatch,
    detect_keywords,
    detect_primary_keyword,
    is_underspecified_for_execution,
    apply_ralplan_gate,
    get_all_keywords_with_size_check,
)
from .keyword_registry import (
    KeywordTriggerDefinition,
    KEYWORD_TRIGGER_DEFINITIONS,
    compare_keyword_matches,
)
from .session import (
    SessionState,
    read_session_state,
    write_session_start,
    write_session_end,
    is_session_stale,
    append_to_log,
)
from .codebase_map import generate_codebase_map
from .explore_routing import (
    is_explore_command_routing_enabled,
    is_simple_exploration_prompt,
    build_explore_routing_guidance,
)
from .agents_overlay import (
    generate_overlay,
    apply_overlay,
    strip_overlay,
    has_overlay,
)
from .task_size_detector import (
    TaskSize,
    TaskSizeResult,
    classify_task_size,
    is_heavy_mode,
    count_words,
)

__all__ = [
    # Plugin system
    "load_plugins",
    "validate_plugin",
    "clear_plugin_cache",
    # Hook registry + dispatcher
    "register_hook",
    "unregister_hook",
    "emit",
    "dispatch",
    "KNOWN_EVENTS",
    "DispatchResult",
    "PluginDispatchResult",
    # Existing exports
    "KeywordMatch",
    "detect_keywords",
    "detect_primary_keyword",
    "is_underspecified_for_execution",
    "apply_ralplan_gate",
    "get_all_keywords_with_size_check",
    "KeywordTriggerDefinition",
    "KEYWORD_TRIGGER_DEFINITIONS",
    "compare_keyword_matches",
    "SessionState",
    "read_session_state",
    "write_session_start",
    "write_session_end",
    "is_session_stale",
    "append_to_log",
    "generate_codebase_map",
    "is_explore_command_routing_enabled",
    "is_simple_exploration_prompt",
    "build_explore_routing_guidance",
    "generate_overlay",
    "apply_overlay",
    "strip_overlay",
    "has_overlay",
    "TaskSize",
    "TaskSizeResult",
    "classify_task_size",
    "is_heavy_mode",
    "count_words",
]
