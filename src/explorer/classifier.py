"""
CommandClassifier — decide whether a command string is safe to run.

Safety rules:
  - Only the allowlisted commands (git log, git diff, ls, rg, etc.) are
    permitted as the root executable.
  - Shell metacharacters that enable composition (pipes, semicolons,
    backticks, process substitution, background jobs) are blocked.
  - Dangerous sub-commands and programs (rm, mv, chmod, sudo, eval, exec, …)
    are blocked regardless of where they appear in the argument list.
  - Absolute paths starting with / are blocked (prevent reading arbitrary FS).
  - Path traversal via ".." is blocked.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Allow / block lists
# ---------------------------------------------------------------------------

# Root executables that are safe in read-only / inspect mode.
ALLOWED_EXECUTABLES = frozenset([
    "git",
    "find",
    "ls",
    "rg",
    "grep",
    "cat",
    "head",
    "tail",
    "wc",
    "file",
    "stat",
    "pwd",
    "echo",
    "printf",
])

# git sub-commands that are safe (read-only inspection).
ALLOWED_GIT_SUBCOMMANDS = frozenset([
    "log",
    "diff",
    "status",
    "show",
    "branch",
    "rev-parse",
    "describe",
    "tag",
    "stash",
    "shortlog",
    "blame",
    "ls-files",
    "ls-tree",
    "remote",
    "config",
])

# Blocked programs / sub-commands.
BLOCKED_PROGRAMS = frozenset([
    "rm", "rmdir", "mv", "cp",
    "chmod", "chown", "chgrp",
    "sudo", "su", "doas",
    "eval", "exec",
    "curl", "wget",
    "dd", "mkfs", "fdisk",
    "kill", "killall",
    "reboot", "shutdown", "halt", "poweroff",
    "python", "python3", "ruby", "perl", "node", "php",
    "bash", "sh", "zsh", "fish", "dash",
    "nc", "netcat", "ncat",
    "ssh", "scp", "sftp", "rsync",
    "xargs",   # can chain arbitrary commands
    "tee",     # writes to files
    "sed",     # can write files with -i
    "awk",     # can write files
    "patch",   # writes files
    "install", # writes files
])

# Shell metacharacter patterns that enable composition.
_SHELL_METACHAR_RE = re.compile(
    r"[|;&`]"           # pipe, semicolon, background, backtick
    r"|\$\("            # process substitution $(...)
    r"|<\("             # process substitution <(...)
    r"|>\("             # process substitution >(...)
    r"|>>|2>&1|>&"      # redirects that write
    r"|>{1}"            # output redirect
)

# Absolute path pattern.
_ABSOLUTE_PATH_RE = re.compile(r"^/")

# Path traversal.
_DOTDOT_RE = re.compile(r"(?:^|/)\.\.(?:/|$)")


# ---------------------------------------------------------------------------
# Classification result
# ---------------------------------------------------------------------------

@dataclass
class ClassificationResult:
    safe: bool
    reason: Optional[str] = None    # human-readable explanation when not safe


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

class CommandClassifier:
    """
    Stateless classifier that evaluates a raw command string or argv list.

    Usage:
        clf = CommandClassifier()
        result = clf.is_safe("git log --oneline -20")
        if not result.safe:
            print(result.reason)
    """

    def _check_metacharacters(self, raw: str) -> Optional[str]:
        m = _SHELL_METACHAR_RE.search(raw)
        if m:
            return f"blocked shell metacharacter: {m.group()!r}"
        return None

    def _check_token_path(self, token: str) -> Optional[str]:
        """Check a single argument token for path violations."""
        if _ABSOLUTE_PATH_RE.match(token):
            return f"absolute path not allowed: {token!r}"
        if _DOTDOT_RE.search(token):
            return f"path traversal (..) not allowed: {token!r}"
        return None

    def _check_blocked_program(self, token: str) -> Optional[str]:
        # Strip any path prefix to get the bare program name.
        name = PurePosixPath(token).name
        if name in BLOCKED_PROGRAMS:
            return f"blocked program or sub-command: {name!r}"
        return None

    def classify(self, command: str) -> ClassificationResult:
        """
        Classify a raw command string (may contain flags and arguments).

        Returns ClassificationResult(safe=True) when the command is safe.
        Returns ClassificationResult(safe=False, reason=...) otherwise.
        """
        if not command or not command.strip():
            return ClassificationResult(safe=False, reason="empty command")

        # Step 1: metacharacter scan on the raw string before tokenisation.
        reason = self._check_metacharacters(command)
        if reason:
            return ClassificationResult(safe=False, reason=reason)

        # Step 2: tokenise with shlex so we work with actual argv components.
        try:
            tokens = shlex.split(command)
        except ValueError as exc:
            return ClassificationResult(safe=False, reason=f"cannot parse command: {exc}")

        if not tokens:
            return ClassificationResult(safe=False, reason="empty command after parsing")

        executable = PurePosixPath(tokens[0]).name

        # Step 3: executable must be in the allowlist.
        if executable not in ALLOWED_EXECUTABLES:
            return ClassificationResult(
                safe=False,
                reason=f"executable not in allowlist: {executable!r}",
            )

        # Step 4: git sub-command gate.
        if executable == "git":
            # Find the first non-flag argument — that's the sub-command.
            sub = next((t for t in tokens[1:] if not t.startswith("-")), None)
            if sub is None:
                return ClassificationResult(safe=False, reason="git requires a sub-command")
            if sub not in ALLOWED_GIT_SUBCOMMANDS:
                return ClassificationResult(
                    safe=False,
                    reason=f"git sub-command not in allowlist: {sub!r}",
                )

        # Step 5: scan every argument token.
        for token in tokens[1:]:
            reason = self._check_blocked_program(token)
            if reason:
                return ClassificationResult(safe=False, reason=reason)
            reason = self._check_token_path(token)
            if reason:
                return ClassificationResult(safe=False, reason=reason)

        return ClassificationResult(safe=True)

    def is_safe(self, command: str) -> bool:
        """Convenience wrapper that returns a plain bool."""
        return self.classify(command).safe
