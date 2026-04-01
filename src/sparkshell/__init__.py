"""pyclaude-sparkshell: Execute commands and optionally summarize large output via codex."""

from __future__ import annotations

import sys
from typing import List, Optional

from ..mux import build_capture_pane_args
from .codex_bridge import summarize_output
from .error import SparkshellError
from .exec_runner import execute_command
from .threshold import combined_visible_lines, read_line_threshold

DEFAULT_TMUX_TAIL_LINES = 200
MIN_TMUX_TAIL_LINES = 100
MAX_TMUX_TAIL_LINES = 1000


def _usage_text() -> str:
    return (
        f"usage: pyclaude-sparkshell <command> [args...]\n"
        f"   or: pyclaude-sparkshell --tmux-pane <pane-id> [--tail-lines <{MIN_TMUX_TAIL_LINES}-{MAX_TMUX_TAIL_LINES}>]\n"
        f"\n"
        f"Direct command mode executes argv without shell metacharacter parsing.\n"
        f"Tmux pane mode captures a larger pane tail and applies the same raw-vs-summary behavior.\n"
    )


def _parse_input(args: List[str]):
    """Returns ('command', argv) or ('tmux_pane', pane_id, tail_lines)."""
    if not args:
        raise SparkshellError.invalid_args(_usage_text())

    pane_id = None
    tail_lines = DEFAULT_TMUX_TAIL_LINES
    explicit_tail = False
    positional = []

    i = 0
    while i < len(args):
        token = args[i]
        if token == "--tmux-pane":
            if i + 1 >= len(args) or args[i + 1].startswith("-"):
                raise SparkshellError.invalid_args("--tmux-pane requires a pane id")
            pane_id = args[i + 1]
            i += 2
            continue
        if token.startswith("--tmux-pane="):
            val = token.split("=", 1)[1]
            if not val.strip():
                raise SparkshellError.invalid_args("--tmux-pane requires a pane id")
            pane_id = val
            i += 1
            continue
        if token == "--tail-lines":
            if i + 1 >= len(args):
                raise SparkshellError.invalid_args("--tail-lines requires a numeric value")
            tail_lines = _parse_tail_lines(args[i + 1])
            explicit_tail = True
            i += 2
            continue
        if token.startswith("--tail-lines="):
            tail_lines = _parse_tail_lines(token.split("=", 1)[1])
            explicit_tail = True
            i += 1
            continue
        positional.append(token)
        i += 1

    if pane_id is not None:
        if positional:
            raise SparkshellError.invalid_args("tmux pane mode does not accept an additional command")
        return ("tmux_pane", pane_id, tail_lines)

    if explicit_tail:
        raise SparkshellError.invalid_args("--tail-lines requires --tmux-pane")

    return ("command", positional)


def _parse_tail_lines(raw: str) -> int:
    try:
        val = int(raw.strip())
    except ValueError:
        val = -1
    if val < MIN_TMUX_TAIL_LINES or val > MAX_TMUX_TAIL_LINES:
        raise SparkshellError.invalid_args(
            f"--tail-lines must be an integer between {MIN_TMUX_TAIL_LINES} and {MAX_TMUX_TAIL_LINES}"
        )
    return val


def run(argv: Optional[List[str]] = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    if argv and argv[0] in ("--help", "-h"):
        print(_usage_text())
        return

    parsed = _parse_input(argv)

    if parsed[0] == "tmux_pane":
        _, pane_id, tail_lines = parsed
        execution_argv = ["tmux"] + build_capture_pane_args(pane_id, tail_lines)
    else:
        _, execution_argv = parsed

    output = execute_command(execution_argv)
    threshold = read_line_threshold()
    line_count = combined_visible_lines(output.stdout, output.stderr)

    if line_count <= threshold:
        sys.stdout.buffer.write(output.stdout)
        sys.stdout.buffer.flush()
        sys.stderr.buffer.write(output.stderr)
        sys.stderr.buffer.flush()
        sys.exit(output.exit_code())

    try:
        summary = summarize_output(execution_argv, output)
        sys.stdout.write(summary)
        if not summary.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()
    except SparkshellError as e:
        sys.stdout.buffer.write(output.stdout)
        sys.stdout.buffer.flush()
        sys.stderr.buffer.write(output.stderr)
        sys.stderr.buffer.flush()
        print(f"omx sparkshell: summary unavailable ({e})", file=sys.stderr)

    sys.exit(output.exit_code())


def main() -> None:
    try:
        run()
    except SparkshellError as e:
        print(f"omx sparkshell: {e}", file=sys.stderr)
        sys.exit(e.raw_exit_code())
    except SystemExit:
        raise
    except Exception as e:
        print(f"omx sparkshell: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
