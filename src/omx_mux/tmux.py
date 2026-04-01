"""Tmux adapter — subprocess wrapper for tmux commands."""

from __future__ import annotations

import subprocess
import time
from typing import List

from .types import (
    InputEnvelope,
    MuxAdapter,
    MuxError,
    MuxOperation,
    MuxOutcome,
    MuxTarget,
)


def run_tmux(args: List[str]) -> str:
    """Run a tmux command. Returns stdout on success, raises MuxError on failure."""
    try:
        result = subprocess.run(
            ["tmux", *args],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise MuxError.adapter_failed(f"failed to run tmux: {exc}") from exc

    if result.returncode == 0:
        return result.stdout
    raise MuxError.adapter_failed(
        f"tmux {args[0] if args else ''} failed: {result.stderr.strip()}"
    )


def resolve_target_handle(target: MuxTarget) -> str:
    if target.is_delivery_handle:
        if not target.handle:
            raise MuxError.invalid_target("empty delivery handle")
        return target.handle
    raise MuxError.invalid_target("cannot operate on a detached target")


def session_from_handle(handle: str) -> str:
    return handle.split(":")[0]


def build_send_keys_args(target: str, text: str) -> List[str]:
    return ["send-keys", "-t", target, "-l", text]


def build_enter_key_args(target: str) -> List[str]:
    return ["send-keys", "-t", target, "C-m"]


def build_capture_pane_args(target: str, visible_lines: int) -> List[str]:
    return ["capture-pane", "-t", target, "-p", "-S", f"-{visible_lines}"]


class TmuxAdapter(MuxAdapter):
    """Concrete tmux adapter that shells out to the tmux binary."""

    def adapter_name(self) -> str:
        return "tmux"

    def status(self) -> str:
        return "tmux adapter ready"

    def execute(self, operation: MuxOperation) -> MuxOutcome:
        kind = operation.kind
        target = operation.target

        if kind == "resolve-target":
            return self._do_resolve_target(target)
        if kind == "send-input":
            return self._do_send_input(target, operation.envelope)
        if kind == "capture-tail":
            return self._do_capture_tail(target, operation.visible_lines)
        if kind == "inspect-liveness":
            return self._do_inspect_liveness(target)
        if kind == "attach":
            return self._do_attach(target)
        if kind == "detach":
            return self._do_detach(target)
        raise MuxError.unsupported(f"unknown operation: {kind}")

    # -- private helpers --

    def _do_resolve_target(self, target: MuxTarget) -> MuxOutcome:
        handle = resolve_target_handle(target)
        pane_list = run_tmux([
            "list-panes", "-a", "-F",
            "#{session_name}:#{window_index}.#{pane_index}",
        ])
        if any(line.strip() == handle for line in pane_list.splitlines()):
            return MuxOutcome.target_resolved(handle)
        raise MuxError.invalid_target(f"pane not found: {handle}")

    def _do_send_input(
        self, target: MuxTarget, envelope: InputEnvelope
    ) -> MuxOutcome:
        handle = resolve_target_handle(target)
        text = envelope.normalized_text()
        run_tmux(build_send_keys_args(handle, text))

        if envelope.submit.is_enter:
            for i in range(envelope.submit.presses):
                if i > 0 and envelope.submit.delay_ms > 0:
                    time.sleep(envelope.submit.delay_ms / 1000.0)
                run_tmux(build_enter_key_args(handle))

        return MuxOutcome.input_accepted(len(text))

    def _do_capture_tail(
        self, target: MuxTarget, visible_lines: int
    ) -> MuxOutcome:
        handle = resolve_target_handle(target)
        body = run_tmux(build_capture_pane_args(handle, visible_lines))
        return MuxOutcome.tail_captured(visible_lines, body)

    def _do_inspect_liveness(self, target: MuxTarget) -> MuxOutcome:
        handle = resolve_target_handle(target)
        session = session_from_handle(handle)
        result = subprocess.run(
            ["tmux", "has-session", "-t", session],
            capture_output=True,
        )
        return MuxOutcome.liveness_checked(result.returncode == 0)

    def _do_attach(self, target: MuxTarget) -> MuxOutcome:
        handle = resolve_target_handle(target)
        run_tmux(["attach-session", "-t", handle])
        return MuxOutcome.attached(handle)

    def _do_detach(self, target: MuxTarget) -> MuxOutcome:
        handle = resolve_target_handle(target)
        run_tmux(["detach-client", "-t", handle])
        return MuxOutcome.detached(handle)
