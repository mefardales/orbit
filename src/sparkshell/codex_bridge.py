"""Bridge to codex for output summarization."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from typing import List, Optional, Tuple

from .error import SparkshellError
from .exec_runner import CommandOutput
from .prompt import build_summary_prompt

DEFAULT_SUMMARY_TIMEOUT_MS = 60_000
DEFAULT_SPARK_MODEL = "gpt-5.3-codex-spark"
DEFAULT_FRONTIER_MODEL = "gpt-5.4"


def resolve_model() -> str:
    for var in ("PYCLAUDE_SPARKSHELL_MODEL", "PYCLAUDE_DEFAULT_SPARK_MODEL", "PYCLAUDE_SPARK_MODEL"):
        val = os.environ.get(var, "").strip()
        if val:
            return val
    return DEFAULT_SPARK_MODEL


def resolve_fallback_model() -> str:
    for var in ("PYCLAUDE_SPARKSHELL_FALLBACK_MODEL", "PYCLAUDE_DEFAULT_FRONTIER_MODEL"):
        val = os.environ.get(var, "").strip()
        if val:
            return val
    return DEFAULT_FRONTIER_MODEL


def read_summary_timeout_ms() -> int:
    raw = os.environ.get("PYCLAUDE_SPARKSHELL_SUMMARY_TIMEOUT_MS", "")
    try:
        val = int(raw.strip())
        return val if val > 0 else DEFAULT_SUMMARY_TIMEOUT_MS
    except ValueError:
        return DEFAULT_SUMMARY_TIMEOUT_MS


def summarize_output(command: List[str], output: CommandOutput) -> str:
    prompt = build_summary_prompt(command, output)
    model = resolve_model()
    fallback_model = resolve_fallback_model()
    timeout_ms = read_summary_timeout_ms()

    stdout, stderr, ok = _run_codex_exec(prompt, model, timeout_ms)
    if not ok:
        if fallback_model != model and _should_retry_with_fallback(stderr):
            fb_stdout, fb_stderr, fb_ok = _run_codex_exec(prompt, fallback_model, timeout_ms)
            if not fb_ok:
                primary_msg = stderr.strip() or "codex exec exited unsuccessfully"
                fallback_msg = fb_stderr.strip() or "codex exec exited unsuccessfully"
                raise SparkshellError.summary_bridge(
                    f"codex exec failed for primary model `{model}` ({primary_msg}) "
                    f"and fallback model `{fallback_model}` ({fallback_msg})"
                )
            result = _normalize_summary(fb_stdout)
            if result is None:
                raise SparkshellError.summary_bridge("codex exec fallback returned no valid summary sections")
            return result

        msg = stderr.strip() or "codex exec exited unsuccessfully"
        raise SparkshellError.summary_bridge(f"codex exec exited unsuccessfully: {msg}" if stderr.strip() else msg)

    result = _normalize_summary(stdout)
    if result is None:
        raise SparkshellError.summary_bridge("codex exec returned no valid summary sections")
    return result


_RETRY_KEYWORDS = [
    "quota", "rate limit", "429", "unavailable", "not available",
    "unknown model", "model not found", "no access", "capacity",
]


def _should_retry_with_fallback(stderr: str) -> bool:
    lower = stderr.lower()
    return any(kw in lower for kw in _RETRY_KEYWORDS)


def _run_codex_exec(prompt: str, model: str, timeout_ms: int) -> Tuple[str, str, bool]:
    cmd = [
        "codex", "exec",
        "--model", model,
        "--sandbox", "read-only",
        "-c", 'model_reasoning_effort="low"',
        "--skip-git-repo-check",
        "--color", "never",
        "-",
    ]
    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout_ms / 1000.0,
        )
    except subprocess.TimeoutExpired:
        raise SparkshellError.summary_timeout(timeout_ms)
    except FileNotFoundError as e:
        raise SparkshellError.summary_bridge(f"failed to run codex: {e}")

    return result.stdout, result.stderr, result.returncode == 0


def _normalize_summary(raw: str) -> Optional[str]:
    summary: List[str] = []
    failures: List[str] = []
    warnings: List[str] = []
    current: Optional[List[str]] = None

    for line in raw.splitlines():
        trimmed = line.strip()
        if not trimmed:
            continue
        normalized = trimmed.lstrip("-* ").lower()

        if normalized.startswith("summary:"):
            rest = normalized[len("summary:"):].strip()
            summary.append(rest)
            current = summary
            continue
        if normalized.startswith("failures:"):
            rest = normalized[len("failures:"):].strip()
            failures.append(rest)
            current = failures
            continue
        if normalized.startswith("warnings:"):
            rest = normalized[len("warnings:"):].strip()
            warnings.append(rest)
            current = warnings
            continue

        if ":" in trimmed and not line.startswith((" ", "\t")):
            current = None
            continue

        if current is not None:
            current.append(trimmed)

    rendered = []
    for name, entries in [("summary", summary), ("failures", failures), ("warnings", warnings)]:
        if entries:
            rendered.append(_render_section(name, entries))

    return "\n".join(rendered) if rendered else None


def _render_section(name: str, entries: List[str]) -> str:
    head = entries[0].strip() if entries else ""
    lines = [f"- {name}: {head}"]
    for entry in entries[1:]:
        t = entry.strip()
        if t:
            lines.append(f"  - {t}")
    return "\n".join(lines)
