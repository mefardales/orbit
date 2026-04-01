"""
Tool permission enforcement for orbit.

Provides ToolPermissionManager for rule-based tool allow/deny decisions,
PermissionContext for tracking denied attempts during a session, and audit
logging to .orbit/state/permission-audit.json.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

# ── Constants ────────────────────────────────────────────────────────────────

_PERMISSIONS_FILE = Path(".orbit") / "permissions.json"
_AUDIT_FILE = Path(".orbit") / "state" / "permission-audit.json"

PermissionResult = Literal["allowed", "denied", "ask"]

# Tools that are dangerous by default — deny unless the user explicitly allows them
_DEFAULT_DENY_NAMES: List[str] = [
    "rm",
    "rmdir",
    "sudo",
    "eval",
    "exec",
    "shell",
    "bash",
    "sh",
    "powershell",
    "cmd",
    "chmod",
    "chown",
    "dd",
    "mkfs",
    "format",
    "regedit",
    "kill",
    "pkill",
]

_DEFAULT_DENY_PREFIXES: List[str] = [
    "sudo_",
    "dangerous_",
    "unsafe_",
]


# ── Kept for backward compat: the original frozen dataclass ──────────────────


@dataclass(frozen=True)
class ToolPermissionContext:
    """Immutable permission context (original interface — kept for main.py).

    Used by the 'orbit tools' CLI command to filter the tool list.
    """

    deny_names: frozenset[str] = field(default_factory=frozenset)
    deny_prefixes: tuple[str, ...] = ()

    @classmethod
    def from_iterables(
        cls,
        deny_names: Optional[List[str]] = None,
        deny_prefixes: Optional[List[str]] = None,
    ) -> "ToolPermissionContext":
        return cls(
            deny_names=frozenset(name.lower() for name in (deny_names or [])),
            deny_prefixes=tuple(prefix.lower() for prefix in (deny_prefixes or [])),
        )

    def blocks(self, tool_name: str) -> bool:
        lowered = tool_name.lower()
        return lowered in self.deny_names or any(
            lowered.startswith(prefix) for prefix in self.deny_prefixes
        )


# ── Permission rules ──────────────────────────────────────────────────────────


@dataclass
class PermissionRules:
    """Mutable set of allow/deny rules loaded from disk."""

    allow_names: List[str] = field(default_factory=list)
    deny_names: List[str] = field(default_factory=list)
    deny_prefixes: List[str] = field(default_factory=list)
    # Tools in 'ask' require interactive confirmation
    ask_names: List[str] = field(default_factory=list)
    ask_prefixes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allow_names": self.allow_names,
            "deny_names": self.deny_names,
            "deny_prefixes": self.deny_prefixes,
            "ask_names": self.ask_names,
            "ask_prefixes": self.ask_prefixes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PermissionRules":
        return cls(
            allow_names=data.get("allow_names", []),
            deny_names=data.get("deny_names", []),
            deny_prefixes=data.get("deny_prefixes", []),
            ask_names=data.get("ask_names", []),
            ask_prefixes=data.get("ask_prefixes", []),
        )


def _load_rules(path: Path) -> PermissionRules:
    if not path.exists():
        return PermissionRules()
    try:
        data = json.loads(path.read_text("utf-8"))
        return PermissionRules.from_dict(data)
    except (json.JSONDecodeError, OSError):
        return PermissionRules()


def _save_rules(rules: PermissionRules, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rules.to_dict(), indent=2), encoding="utf-8")


# ── Audit log ────────────────────────────────────────────────────────────────


@dataclass
class AuditEntry:
    """A single permission decision recorded in the audit log."""

    timestamp: float
    tool_name: str
    result: PermissionResult
    reason: str
    session_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "tool_name": self.tool_name,
            "result": self.result,
            "reason": self.reason,
            "session_id": self.session_id,
        }


def _append_audit(entry: AuditEntry, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    entries: List[Dict[str, Any]] = []
    if path.exists():
        try:
            entries = json.loads(path.read_text("utf-8"))
            if not isinstance(entries, list):
                entries = []
        except (json.JSONDecodeError, OSError):
            entries = []
    entries.append(entry.to_dict())
    path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


# ── PermissionContext ─────────────────────────────────────────────────────────


@dataclass
class PermissionContext:
    """Session-scoped context that tracks denied tool invocation attempts.

    Passed to tool execution sites so that denied invocations are captured
    in memory and optionally flushed to the audit log.
    """

    session_id: Optional[str] = None
    _denied_attempts: List[Dict[str, Any]] = field(default_factory=list, repr=False)
    _audit_path: Path = field(default=_AUDIT_FILE, repr=False)

    def record_denied(self, tool_name: str, reason: str) -> None:
        """Record a tool invocation that was denied."""
        entry = {
            "tool_name": tool_name,
            "reason": reason,
            "timestamp": time.time(),
        }
        self._denied_attempts.append(entry)
        _append_audit(
            AuditEntry(
                timestamp=entry["timestamp"],
                tool_name=tool_name,
                result="denied",
                reason=reason,
                session_id=self.session_id,
            ),
            self._audit_path,
        )

    def record_allowed(self, tool_name: str, reason: str = "allowed by rule") -> None:
        """Optionally record an allowed invocation for audit purposes."""
        _append_audit(
            AuditEntry(
                timestamp=time.time(),
                tool_name=tool_name,
                result="allowed",
                reason=reason,
                session_id=self.session_id,
            ),
            self._audit_path,
        )

    @property
    def denied_attempts(self) -> List[Dict[str, Any]]:
        return list(self._denied_attempts)

    @property
    def denied_count(self) -> int:
        return len(self._denied_attempts)


# ── ToolPermissionManager ─────────────────────────────────────────────────────


class ToolPermissionManager:
    """Rule-based tool permission enforcement.

    Rules are loaded from .orbit/permissions.json. Default deny rules for
    dangerous tools are applied before file-based rules, but explicit
    allow_names entries in the file can override them.
    """

    def __init__(
        self,
        rules_path: Optional[Path] = None,
        audit_path: Optional[Path] = None,
        *,
        apply_defaults: bool = True,
    ) -> None:
        self._rules_path = rules_path or _PERMISSIONS_FILE
        self._audit_path = audit_path or _AUDIT_FILE
        self._apply_defaults = apply_defaults
        self._rules: Optional[PermissionRules] = None

    # ── Rules loading ─────────────────────────────────────────────────────────

    def _get_rules(self) -> PermissionRules:
        """Load rules from disk (cached until invalidated)."""
        if self._rules is None:
            self._rules = _load_rules(self._rules_path)
        return self._rules

    def _invalidate(self) -> None:
        self._rules = None

    # ── Core decision logic ───────────────────────────────────────────────────

    def check_permission(self, tool_name: str) -> PermissionResult:
        """Determine whether *tool_name* may be invoked.

        Decision order:
        1. If the tool is in the explicit allow list → "allowed"
        2. If the tool matches a deny rule (name or prefix) → "denied"
        3. If the tool matches an ask rule (name or prefix) → "ask"
        4. If default deny rules are enabled and the tool is in them → "denied"
        5. Otherwise → "allowed"

        Args:
            tool_name: The tool identifier to check.

        Returns:
            'allowed', 'denied', or 'ask'.
        """
        rules = self._get_rules()
        lower = tool_name.lower()

        # 1. Explicit allow overrides everything
        if lower in (n.lower() for n in rules.allow_names):
            return "allowed"

        # 2. Explicit deny by name
        if lower in (n.lower() for n in rules.deny_names):
            return "denied"

        # 3. Explicit deny by prefix
        if any(lower.startswith(p.lower()) for p in rules.deny_prefixes):
            return "denied"

        # 4. Ask by name
        if lower in (n.lower() for n in rules.ask_names):
            return "ask"

        # 5. Ask by prefix
        if any(lower.startswith(p.lower()) for p in rules.ask_prefixes):
            return "ask"

        # 6. Default deny list
        if self._apply_defaults:
            if lower in (n.lower() for n in _DEFAULT_DENY_NAMES):
                return "denied"
            if any(lower.startswith(p.lower()) for p in _DEFAULT_DENY_PREFIXES):
                return "denied"

        return "allowed"

    # ── Rule mutation ─────────────────────────────────────────────────────────

    def allow_tool(self, name: str) -> None:
        """Add *name* to the allow list, removing it from deny lists if present."""
        rules = self._get_rules()
        lower = name.lower()
        if lower not in (n.lower() for n in rules.allow_names):
            rules.allow_names.append(name)
        # Remove from deny lists
        rules.deny_names = [n for n in rules.deny_names if n.lower() != lower]
        rules.ask_names = [n for n in rules.ask_names if n.lower() != lower]
        _save_rules(rules, self._rules_path)

    def deny_tool(self, name: str) -> None:
        """Add *name* to the deny list, removing it from allow/ask lists."""
        rules = self._get_rules()
        lower = name.lower()
        if lower not in (n.lower() for n in rules.deny_names):
            rules.deny_names.append(name)
        rules.allow_names = [n for n in rules.allow_names if n.lower() != lower]
        rules.ask_names = [n for n in rules.ask_names if n.lower() != lower]
        _save_rules(rules, self._rules_path)

    def ask_tool(self, name: str) -> None:
        """Add *name* to the ask list (require interactive confirmation)."""
        rules = self._get_rules()
        lower = name.lower()
        if lower not in (n.lower() for n in rules.ask_names):
            rules.ask_names.append(name)
        rules.deny_names = [n for n in rules.deny_names if n.lower() != lower]
        rules.allow_names = [n for n in rules.allow_names if n.lower() != lower]
        _save_rules(rules, self._rules_path)

    def deny_prefix(self, prefix: str) -> None:
        """Deny all tools whose names start with *prefix*."""
        rules = self._get_rules()
        lower = prefix.lower()
        if lower not in (p.lower() for p in rules.deny_prefixes):
            rules.deny_prefixes.append(prefix)
        rules.ask_prefixes = [p for p in rules.ask_prefixes if p.lower() != lower]
        _save_rules(rules, self._rules_path)

    def allow_prefix(self, prefix: str) -> None:
        """Remove a deny_prefix entry so matching tools are no longer blanket-denied."""
        rules = self._get_rules()
        lower = prefix.lower()
        rules.deny_prefixes = [p for p in rules.deny_prefixes if p.lower() != lower]
        _save_rules(rules, self._rules_path)

    # ── Query helpers ─────────────────────────────────────────────────────────

    def get_denied_tools(self) -> List[str]:
        """Return all tool names in the explicit deny list."""
        return list(self._get_rules().deny_names)

    def get_allowed_tools(self) -> List[str]:
        """Return all tool names in the explicit allow list."""
        return list(self._get_rules().allow_names)

    def get_denied_prefixes(self) -> List[str]:
        """Return all deny prefix patterns."""
        return list(self._get_rules().deny_prefixes)

    def get_effective_defaults(self) -> Dict[str, List[str]]:
        """Return the built-in default deny rules currently in effect."""
        if not self._apply_defaults:
            return {"deny_names": [], "deny_prefixes": []}
        return {
            "deny_names": list(_DEFAULT_DENY_NAMES),
            "deny_prefixes": list(_DEFAULT_DENY_PREFIXES),
        }

    # ── Audit helpers ─────────────────────────────────────────────────────────

    def read_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return the most recent audit entries, newest first."""
        if not self._audit_path.exists():
            return []
        try:
            entries = json.loads(self._audit_path.read_text("utf-8"))
            if not isinstance(entries, list):
                return []
            return list(reversed(entries[-limit:]))
        except (json.JSONDecodeError, OSError):
            return []

    def new_context(self, session_id: Optional[str] = None) -> PermissionContext:
        """Create a new PermissionContext for a single session/invocation."""
        return PermissionContext(session_id=session_id, _audit_path=self._audit_path)

    # ── Compatibility: build a ToolPermissionContext (legacy frozen dataclass) ─

    def to_permission_context(self) -> ToolPermissionContext:
        """Build the legacy immutable ToolPermissionContext from current rules.

        Used by CLI callers that still rely on the original interface.
        """
        rules = self._get_rules()
        all_deny_names = list(rules.deny_names)
        if self._apply_defaults:
            all_deny_names.extend(_DEFAULT_DENY_NAMES)
        all_deny_prefixes = list(rules.deny_prefixes)
        if self._apply_defaults:
            all_deny_prefixes.extend(_DEFAULT_DENY_PREFIXES)
        return ToolPermissionContext.from_iterables(all_deny_names, all_deny_prefixes)


# ── Module-level default manager ─────────────────────────────────────────────

_default_manager = ToolPermissionManager()


def get_permission_manager() -> ToolPermissionManager:
    """Return the module-level default ToolPermissionManager."""
    return _default_manager
