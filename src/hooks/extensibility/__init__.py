"""
Hook extensibility framework for orbit.

Provides plugin discovery, loading, event dispatch, and type definitions
for extending orbit with custom hook plugins.
"""

from .types import (
    HookSchemaVersion,
    HookEventSource,
    HookEventName,
    HookEventEnvelope,
    HookPluginDescriptor,
    HookPluginDispatchResult,
    HookDispatchResult,
    HookDispatchOptions,
)
from .events import (
    build_hook_event,
    build_native_hook_event,
    build_derived_hook_event,
    is_derived_event_name,
)
from .dispatcher import dispatch_hook_event, is_hook_plugin_feature_enabled
from .loader import (
    discover_hook_plugins,
    load_hook_plugin_descriptors,
    is_hook_plugins_enabled,
    hooks_dir,
    ensure_hooks_dir,
)

__all__ = [
    "HookSchemaVersion",
    "HookEventSource",
    "HookEventName",
    "HookEventEnvelope",
    "HookPluginDescriptor",
    "HookPluginDispatchResult",
    "HookDispatchResult",
    "HookDispatchOptions",
    "build_hook_event",
    "build_native_hook_event",
    "build_derived_hook_event",
    "is_derived_event_name",
    "dispatch_hook_event",
    "is_hook_plugin_feature_enabled",
    "discover_hook_plugins",
    "load_hook_plugin_descriptors",
    "is_hook_plugins_enabled",
    "hooks_dir",
    "ensure_hooks_dir",
]
