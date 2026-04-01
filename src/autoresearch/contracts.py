"""
Autoresearch contracts module.

Ported from pyclaude src/autoresearch/contracts.ts.
Defines data structures and parsing/validation logic for autoresearch
missions, sandbox configurations, and evaluator results.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

AutoresearchKeepPolicy = Literal["score_improvement", "pass_only"]

# ---------------------------------------------------------------------------
# Error constants
# ---------------------------------------------------------------------------

_MISSION_DIR_GIT_ERROR = "mission-dir must be inside a git repository."
_SANDBOX_FRONTMATTER_ERROR = (
    "sandbox.md must start with YAML frontmatter containing "
    "evaluator.command and evaluator.format=json."
)
_EVALUATOR_BLOCK_ERROR = "sandbox.md frontmatter must define an evaluator block."
_EVALUATOR_COMMAND_ERROR = "sandbox.md frontmatter evaluator.command is required."
_EVALUATOR_FORMAT_REQUIRED_ERROR = (
    "sandbox.md frontmatter evaluator.format is required and must be json "
    "in autoresearch v1."
)
_EVALUATOR_FORMAT_JSON_ERROR = (
    "sandbox.md frontmatter evaluator.format must be json in autoresearch v1."
)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AutoresearchEvaluatorContract:
    """Specifies how to invoke and interpret the evaluator command."""

    command: str
    format: Literal["json"] = "json"
    keep_policy: Optional[AutoresearchKeepPolicy] = None


@dataclass
class ParsedSandboxContract:
    """Parsed sandbox.md: extracted frontmatter, evaluator settings, and body."""

    frontmatter: dict[str, Any] = field(default_factory=dict)
    evaluator: AutoresearchEvaluatorContract = field(
        default_factory=lambda: AutoresearchEvaluatorContract(command="")
    )
    body: str = ""


@dataclass
class AutoresearchEvaluatorResult:
    """Evaluator output with required boolean ``pass_`` and optional ``score``."""

    pass_: bool
    score: Optional[float] = None


@dataclass
class AutoresearchMissionContract:
    """Top-level mission contract loaded from a mission directory."""

    mission_dir: str = ""
    repo_root: str = ""
    mission_file: str = ""
    sandbox_file: str = ""
    mission_relative_dir: str = ""
    mission_content: str = ""
    sandbox_content: str = ""
    sandbox: ParsedSandboxContract = field(default_factory=ParsedSandboxContract)
    mission_slug: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify_mission_name(value: str) -> str:
    """Convert a directory name to a URL-safe slug (max 48 chars)."""
    slug = _SLUG_RE.sub("-", value.lower()).strip("-")[:48]
    return slug or "mission"


class ContractError(Exception):
    """Raised when a contract validation check fails."""


def _contract_error(message: str) -> ContractError:
    return ContractError(message)


def _read_git(repo_path: str, args: list[str]) -> str:
    """Run a git command and return trimmed stdout."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise _contract_error(stderr or _MISSION_DIR_GIT_ERROR) from exc


def _ensure_path_inside(parent_path: str, child_path: str) -> None:
    """Verify *child_path* is inside *parent_path*."""
    try:
        Path(child_path).resolve().relative_to(Path(parent_path).resolve())
    except ValueError:
        raise _contract_error(_MISSION_DIR_GIT_ERROR)


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(
    r"^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$"
)


def _extract_frontmatter(content: str) -> tuple[str, str]:
    """Split markdown content into (frontmatter_yaml, body)."""
    m = _FRONTMATTER_RE.match(content)
    if not m:
        raise _contract_error(_SANDBOX_FRONTMATTER_ERROR)
    return m.group(1) or "", (m.group(2) or "").strip()


def _parse_simple_yaml_frontmatter(frontmatter: str) -> dict[str, Any]:
    """Minimal YAML parser supporting one level of nesting."""
    result: dict[str, Any] = {}
    current_section: str | None = None

    for raw_line in frontmatter.split("\n"):
        line = raw_line.replace("\t", "  ")
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#"):
            continue

        # Section header (key with no value)
        section_match = re.match(r"^([A-Za-z0-9_-]+):\s*$", trimmed)
        if section_match:
            current_section = section_match.group(1)
            result[current_section] = {}
            continue

        # Key-value pair
        kv_match = re.match(r"^([A-Za-z0-9_-]+):\s*(.+)\s*$", trimmed)
        if not kv_match:
            raise _contract_error(
                f"Unsupported sandbox.md frontmatter line: {trimmed}"
            )

        key = kv_match.group(1)
        raw_value = kv_match.group(2)
        value = raw_value.strip("'\"")

        if line.startswith(" ") or line.startswith("\t"):
            if current_section is None:
                raise _contract_error(
                    f"Nested sandbox.md frontmatter key requires a parent "
                    f"section: {trimmed}"
                )
            section = result[current_section]
            if not isinstance(section, dict):
                raise _contract_error(
                    f"Invalid sandbox.md frontmatter section: {current_section}"
                )
            section[key] = value
            continue

        result[key] = value
        current_section = None

    return result


def _parse_keep_policy(raw: Any) -> AutoresearchKeepPolicy | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise _contract_error(
            "sandbox.md frontmatter evaluator.keep_policy must be a string "
            "when provided."
        )
    normalized = raw.strip().lower()
    if not normalized:
        return None
    if normalized == "pass_only":
        return "pass_only"
    if normalized == "score_improvement":
        return "score_improvement"
    raise _contract_error(
        "sandbox.md frontmatter evaluator.keep_policy must be one of: "
        "score_improvement, pass_only."
    )


# ---------------------------------------------------------------------------
# Public parsing functions
# ---------------------------------------------------------------------------


def parse_sandbox_contract(content: str) -> ParsedSandboxContract:
    """Parse sandbox.md content into a :class:`ParsedSandboxContract`.

    Validates that the file has YAML frontmatter with an evaluator block
    containing ``command`` and ``format: json``.
    """
    frontmatter_str, body = _extract_frontmatter(content)
    parsed_frontmatter = _parse_simple_yaml_frontmatter(frontmatter_str)
    evaluator_raw = parsed_frontmatter.get("evaluator")

    if not evaluator_raw or not isinstance(evaluator_raw, dict):
        raise _contract_error(_EVALUATOR_BLOCK_ERROR)

    command = str(evaluator_raw.get("command", "")).strip()
    fmt = str(evaluator_raw.get("format", "")).strip().lower()
    keep_policy = _parse_keep_policy(evaluator_raw.get("keep_policy"))

    if not command:
        raise _contract_error(_EVALUATOR_COMMAND_ERROR)
    if not fmt:
        raise _contract_error(_EVALUATOR_FORMAT_REQUIRED_ERROR)
    if fmt != "json":
        raise _contract_error(_EVALUATOR_FORMAT_JSON_ERROR)

    evaluator = AutoresearchEvaluatorContract(
        command=command,
        format="json",
        keep_policy=keep_policy,
    )

    return ParsedSandboxContract(
        frontmatter=parsed_frontmatter,
        evaluator=evaluator,
        body=body,
    )


def parse_evaluator_result(raw: str) -> AutoresearchEvaluatorResult:
    """Parse JSON evaluator output into an :class:`AutoresearchEvaluatorResult`.

    Requires boolean ``pass`` and optionally numeric ``score``.
    """
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise _contract_error(
            "Evaluator output must be valid JSON with required boolean pass "
            "and optional numeric score."
        )

    if not isinstance(parsed, dict):
        raise _contract_error("Evaluator output must be a JSON object.")

    if not isinstance(parsed.get("pass"), bool):
        raise _contract_error("Evaluator output must include boolean pass.")

    score = parsed.get("score")
    if score is not None and not isinstance(score, (int, float)):
        raise _contract_error(
            "Evaluator output score must be numeric when provided."
        )

    return AutoresearchEvaluatorResult(
        pass_=parsed["pass"],
        score=float(score) if score is not None else None,
    )


async def load_autoresearch_mission_contract(
    mission_dir_arg: str,
) -> AutoresearchMissionContract:
    """Load a full mission contract from a mission directory.

    The directory must be inside a git repository and contain both
    ``mission.md`` and ``sandbox.md``.
    """
    mission_dir = str(Path(mission_dir_arg).resolve())
    if not Path(mission_dir).exists():
        raise _contract_error(f"mission-dir does not exist: {mission_dir}")

    repo_root = _read_git(mission_dir, ["rev-parse", "--show-toplevel"])
    _ensure_path_inside(repo_root, mission_dir)

    mission_file = str(Path(mission_dir) / "mission.md")
    sandbox_file = str(Path(mission_dir) / "sandbox.md")

    if not Path(mission_file).exists():
        raise _contract_error(
            f"mission.md is required inside mission-dir: {mission_file}"
        )
    if not Path(sandbox_file).exists():
        raise _contract_error(
            f"sandbox.md is required inside mission-dir: {sandbox_file}"
        )

    mission_content = Path(mission_file).read_text(encoding="utf-8")
    sandbox_content = Path(sandbox_file).read_text(encoding="utf-8")
    sandbox = parse_sandbox_contract(sandbox_content)

    mission_relative_dir = str(
        Path(mission_dir).resolve().relative_to(Path(repo_root).resolve())
    ) or Path(mission_dir).name
    mission_slug = slugify_mission_name(mission_relative_dir)

    return AutoresearchMissionContract(
        mission_dir=mission_dir,
        repo_root=repo_root,
        mission_file=mission_file,
        sandbox_file=sandbox_file,
        mission_relative_dir=mission_relative_dir,
        mission_content=mission_content,
        sandbox_content=sandbox_content,
        sandbox=sandbox,
        mission_slug=mission_slug,
    )
