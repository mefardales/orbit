"""Prompt construction and command family classification."""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import List

from .exec_runner import CommandOutput

DEFAULT_SUMMARY_MAX_LINES = 400
DEFAULT_SUMMARY_MAX_BYTES = 24_000


@dataclass
class CommandFamily:
    key: str
    pattern: str
    description: str
    what_it_does: str


_FAMILIES = {
    "git": CommandFamily("git", "git", "Git porcelain and repository inspection commands.",
                         "Reads or changes repository state, history, branches, or working tree diffs."),
    "npm": CommandFamily("node-js", "npm|npx|pnpm|yarn|bun|node",
                         "Node.js package management and build/test tooling.",
                         "Installs dependencies, runs scripts, builds projects, or executes JavaScript tooling."),
    "python": CommandFamily("python", "python|python3|pip|uv|poetry|pytest",
                            "Python interpreter, packaging, and test commands.",
                            "Runs Python code, manages packages, or executes Python-focused tests and tooling."),
    "cargo": CommandFamily("rust", "cargo|rustc", "Rust package, build, and test commands.",
                           "Builds, checks, formats, lints, runs, or tests Rust projects."),
    "go": CommandFamily("go", "go", "Go toolchain commands.",
                        "Builds, formats, manages modules, or tests Go projects."),
    "bundle": CommandFamily("ruby", "bundle|bundler|rake|ruby",
                            "Ruby dependency and task runner commands.",
                            "Runs Ruby code, dependency workflows, or Ruby project tasks."),
    "mvn": CommandFamily("java-kotlin", "mvn|gradle|gradlew|java|kotlinc",
                         "Java and Kotlin build commands.",
                         "Builds, tests, or runs JVM-based projects and wrappers."),
    "make": CommandFamily("c-cpp", "make|cmake|gcc|g++|clang|clang++",
                          "C and C++ build tooling.",
                          "Configures, compiles, or builds native C/C++ projects."),
    "dotnet": CommandFamily("csharp", "dotnet", ".NET SDK commands.",
                            "Builds, restores, runs, or tests .NET applications."),
    "swift": CommandFamily("swift", "swift|xcodebuild",
                           "Swift Package Manager and Xcode build commands.",
                           "Builds, tests, or packages Swift and Apple-platform projects."),
}

_GENERIC_SHELL = CommandFamily(
    "generic-shell",
    "ls|cat|find|grep|sed|awk|xargs|env|echo|pwd|which|sh|bash|zsh",
    "General shell and filesystem inspection commands.",
    "Inspects files, text, environment state, and shell-visible system output.",
)

_EXECUTABLE_MAP = {
    "git": "git",
    "npm": "npm", "npx": "npm", "pnpm": "npm", "yarn": "npm", "bun": "npm", "node": "npm",
    "python": "python", "python3": "python", "pip": "python", "uv": "python", "poetry": "python", "pytest": "python",
    "cargo": "cargo", "rustc": "cargo",
    "go": "go",
    "bundle": "bundle", "bundler": "bundle", "rake": "bundle", "ruby": "bundle",
    "mvn": "mvn", "gradle": "mvn", "gradlew": "mvn", "java": "mvn", "kotlinc": "mvn",
    "make": "make", "cmake": "make", "gcc": "make", "g++": "make", "clang": "make", "clang++": "make",
    "dotnet": "dotnet",
    "swift": "swift", "xcodebuild": "swift",
}


def select_command_family(command: str) -> CommandFamily:
    basename = Path(command).name
    key = _EXECUTABLE_MAP.get(basename)
    if key:
        return _FAMILIES[key]
    return _GENERIC_SHELL


def _count_lines(text: str) -> int:
    if not text:
        return 0
    return len(text.splitlines())


def _read_env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    try:
        val = int(raw.strip())
        return val if val > 0 else default
    except ValueError:
        return default


def _truncate_for_prompt(text: str, label: str) -> str:
    max_lines = _read_env_int("ORBIT_SPARKSHELL_SUMMARY_MAX_LINES", DEFAULT_SUMMARY_MAX_LINES)
    max_bytes = _read_env_int("ORBIT_SPARKSHELL_SUMMARY_MAX_BYTES", DEFAULT_SUMMARY_MAX_BYTES)

    total_lines = _count_lines(text)
    total_bytes = len(text)
    truncated = text

    if total_lines > max_lines:
        lines = text.splitlines()
        head_count = max_lines // 2
        tail_count = max_lines - head_count
        excerpt = (
            lines[:head_count]
            + [f"[... truncated {label}: omitted {total_lines - max_lines} of {total_lines} total lines ...]"]
            + lines[-tail_count:]
        )
        truncated = "\n".join(excerpt)
        if text.endswith("\n"):
            truncated += "\n"

    if len(truncated) > max_bytes:
        head_bytes = max_bytes // 2
        tail_bytes = max_bytes - head_bytes
        prefix = truncated[:head_bytes]
        suffix = truncated[-tail_bytes:]
        omitted = total_bytes - len(prefix) - len(suffix)
        truncated = f"{prefix}\n[... truncated {label}: omitted approximately {omitted} of {total_bytes} total bytes ...]\n{suffix}"

    return truncated


def _shell_join(command: List[str]) -> str:
    return " ".join(
        part if all(c.isalnum() or c in "-_/.:=" for c in part) else repr(part)
        for part in command
    )


def build_summary_prompt(command: List[str], output: CommandOutput) -> str:
    executable = command[0] if command else "unknown"
    family = select_command_family(executable)
    stdout_text = output.stdout_text()
    stderr_text = output.stderr_text()

    return (
        "You summarize shell command output.\\n"
        "Return markdown bullets only. Allowed top-level sections: summary:, failures:, warnings:.\\n"
        "Do not suggest fixes, next steps, commands, or recommendations.\\n"
        "Keep the summary descriptive and grounded in the provided output.\\n\\n"
        f"Command: {_shell_join(command)}\\n"
        f"Command family: {family.key}\\n"
        f"Family pattern: {family.pattern}\\n"
        f"Family description: {family.description}\\n"
        f"Family what_it_does: {family.what_it_does}\\n"
        f"Exit code: {output.exit_code()}\\n\\n"
        f"STDOUT total lines: {_count_lines(stdout_text)}\\n"
        f"STDOUT total bytes: {len(stdout_text)}\\n"
        f"STDERR total lines: {_count_lines(stderr_text)}\\n"
        f"STDERR total bytes: {len(stderr_text)}\\n\\n"
        f"STDOUT:\\n<<<STDOUT\\n{_truncate_for_prompt(stdout_text, 'stdout')}\\n>>>STDOUT\\n\\n"
        f"STDERR:\\n<<<STDERR\\n{_truncate_for_prompt(stderr_text, 'stderr')}\\n>>>STDERR\\n"
    )
