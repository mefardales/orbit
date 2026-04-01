"""Command family registry for classifying executables."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class CommandFamily:
    name: str
    pattern: str
    executables: List[str]
    description: str
    what_it_does: str


GENERIC_SHELL = CommandFamily(
    name="generic-shell",
    pattern="ls|cat|find|grep|sed|awk|xargs|env|echo|pwd|which|sh|bash|zsh",
    executables=["ls", "cat", "find", "grep", "sed", "awk", "xargs", "env", "echo", "pwd", "which", "sh", "bash", "zsh"],
    description="General shell and filesystem inspection commands.",
    what_it_does="Inspects files, text, environment state, and shell-visible system output.",
)

GIT = CommandFamily(
    name="git", pattern="git", executables=["git"],
    description="Git porcelain and repository inspection commands.",
    what_it_does="Reads or changes repository state, history, branches, or working tree diffs.",
)

NODE_JS = CommandFamily(
    name="node-js", pattern="npm|npx|pnpm|yarn|bun|node",
    executables=["npm", "npx", "pnpm", "yarn", "bun", "node"],
    description="Node.js package management and build/test tooling.",
    what_it_does="Installs dependencies, runs scripts, builds projects, or executes JavaScript tooling.",
)

PYTHON = CommandFamily(
    name="python", pattern="python|python3|pip|uv|poetry|pytest",
    executables=["python", "python3", "pip", "uv", "poetry", "pytest"],
    description="Python interpreter, packaging, and test commands.",
    what_it_does="Runs Python code, manages packages, or executes Python-focused tests and tooling.",
)

RUST = CommandFamily(
    name="rust", pattern="cargo|rustc", executables=["cargo", "rustc"],
    description="Rust package, build, and test commands.",
    what_it_does="Builds, checks, formats, lints, runs, or tests Rust projects.",
)

GO = CommandFamily(
    name="go", pattern="go", executables=["go"],
    description="Go toolchain commands.",
    what_it_does="Builds, formats, manages modules, or tests Go projects.",
)

RUBY = CommandFamily(
    name="ruby", pattern="bundle|bundler|rake|ruby",
    executables=["bundle", "bundler", "rake", "ruby"],
    description="Ruby dependency and task runner commands.",
    what_it_does="Runs Ruby code, dependency workflows, or Ruby project tasks.",
)

JAVA_KOTLIN = CommandFamily(
    name="java-kotlin", pattern="mvn|gradle|gradlew|java|kotlinc",
    executables=["mvn", "gradle", "gradlew", "java", "kotlinc"],
    description="Java and Kotlin build commands.",
    what_it_does="Builds, tests, or runs JVM-based projects and wrappers.",
)

C_CPP = CommandFamily(
    name="c-cpp", pattern="make|cmake|gcc|g++|clang|clang++",
    executables=["make", "cmake", "gcc", "g++", "clang", "clang++"],
    description="C and C++ build tooling.",
    what_it_does="Configures, compiles, or builds native C/C++ projects.",
)

CSHARP = CommandFamily(
    name="csharp", pattern="dotnet", executables=["dotnet"],
    description=".NET SDK commands.",
    what_it_does="Builds, restores, runs, or tests .NET applications.",
)

SWIFT = CommandFamily(
    name="swift", pattern="swift|xcodebuild", executables=["swift", "xcodebuild"],
    description="Swift Package Manager and Xcode build commands.",
    what_it_does="Builds, tests, or packages Swift and Apple-platform projects.",
)

FAMILIES: List[CommandFamily] = [
    GENERIC_SHELL, GIT, NODE_JS, PYTHON, RUST, GO,
    RUBY, JAVA_KOTLIN, C_CPP, CSHARP, SWIFT,
]


def all_families() -> List[CommandFamily]:
    return FAMILIES


def _normalize_program(program: str) -> str:
    basename = Path(program).name
    for suffix in (".exe", ".cmd", ".bat", ".ps1"):
        if basename.endswith(suffix):
            basename = basename[: -len(suffix)]
    return basename


def resolve_family(program: str, args: Optional[List[str]] = None) -> CommandFamily:
    normalized = _normalize_program(program)
    first_arg = _normalize_program(args[0]) if args else None

    for family in FAMILIES:
        if normalized in family.executables:
            return family
        if first_arg and first_arg in family.executables:
            return family
    return GENERIC_SHELL


def resolve_family_from_argv(argv: List[str]) -> CommandFamily:
    if not argv:
        return GENERIC_SHELL
    return resolve_family(argv[0], argv[1:])
