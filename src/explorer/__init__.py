"""omx-explore: Runs codex with a prompt contract, falling back across models."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

CODEX_BIN_ENV = "PYCLAUDE_EXPLORE_CODEX_BIN"
HARNESS_ROOT_ENV = "PYCLAUDE_EXPLORE_ROOT"

ALLOWED_DIRECT_COMMANDS = [
    "rg", "grep", "ls", "find", "wc", "cat", "head", "tail", "pwd", "printf",
]


@dataclass
class Args:
    cwd: Path
    prompt: str
    prompt_file: Path
    spark_model: str
    fallback_model: str


@dataclass
class AttemptResult:
    status_code: int
    stderr: str
    output_markdown: Optional[str]


def parse_args(argv: List[str]) -> Args:
    """Parse CLI arguments into an Args struct."""
    cwd = prompt = prompt_file = spark_model = fallback_model = None
    it = iter(argv)
    for token in it:
        if token == "--cwd":
            cwd = Path(next(it))
        elif token == "--prompt":
            prompt = next(it)
        elif token == "--prompt-file":
            prompt_file = Path(next(it))
        elif token == "--model-spark":
            spark_model = next(it)
        elif token == "--model-fallback":
            fallback_model = next(it)
        elif token in ("--help", "-h"):
            raise SystemExit(_usage())
        else:
            raise SystemExit(f"unknown argument: {token}\n{_usage()}")

    if not all([cwd, prompt, prompt_file, spark_model, fallback_model]):
        raise SystemExit(f"missing required arguments\n{_usage()}")
    return Args(cwd=cwd, prompt=prompt, prompt_file=prompt_file,
                spark_model=spark_model, fallback_model=fallback_model)


def invoke_codex(args: Args, model: str, prompt_contract: str) -> AttemptResult:
    """Invoke the codex binary with a given model and prompt contract."""
    codex_bin = os.environ.get(CODEX_BIN_ENV, "codex")
    cmd = [
        codex_bin, "exec",
        "--model", model,
        "--sandbox", "read-only",
        "-c", 'model_reasoning_effort="low"',
        "--skip-git-repo-check",
        "--color", "never",
        "-q", args.prompt,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(args.cwd),
            input=prompt_contract,
        )
    except FileNotFoundError:
        return AttemptResult(status_code=127, stderr="codex binary not found", output_markdown=None)

    return AttemptResult(
        status_code=result.returncode,
        stderr=result.stderr,
        output_markdown=result.stdout if result.returncode == 0 else None,
    )


def run(argv: Optional[List[str]] = None) -> None:
    """Main entry point."""
    if argv is None:
        argv = sys.argv[1:]
    args = parse_args(argv)
    prompt_contract = args.prompt_file.read_text()

    spark_attempt = invoke_codex(args, args.spark_model, prompt_contract)
    if spark_attempt.status_code == 0 and spark_attempt.output_markdown:
        print(spark_attempt.output_markdown, end="")
        return

    print(
        f"[omx explore] spark model `{args.spark_model}` unavailable or failed "
        f"(exit {spark_attempt.status_code}). Falling back to `{args.fallback_model}`.",
        file=sys.stderr,
    )
    if spark_attempt.stderr.strip():
        print(f"[omx explore] spark stderr: {spark_attempt.stderr.strip()}", file=sys.stderr)

    fallback_attempt = invoke_codex(args, args.fallback_model, prompt_contract)
    if fallback_attempt.status_code == 0 and fallback_attempt.output_markdown:
        print(fallback_attempt.output_markdown, end="")
        return

    print(
        f"both spark (`{args.spark_model}`) and fallback (`{args.fallback_model}`) "
        f"attempts failed (codes {spark_attempt.status_code} / {fallback_attempt.status_code}). "
        f"Last stderr: {fallback_attempt.stderr.strip()}",
        file=sys.stderr,
    )
    sys.exit(1)


def main() -> None:
    try:
        run()
    except SystemExit:
        raise
    except Exception as e:
        print(f"[omx explore] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

_usage = lambda: (
    "Usage: omx-explore --cwd <dir> --prompt <text> --prompt-file <explore-prompt.md> "
    "--model-spark <model> --model-fallback <model>"
)
