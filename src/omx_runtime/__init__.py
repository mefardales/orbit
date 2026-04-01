"""omx-runtime: CLI entry point for the runtime engine."""

from __future__ import annotations

import json
import sys
from typing import List, Optional

from ..omx_mux import MuxOperation, MuxTarget, TmuxAdapter, canonical_contract_summary
from ..omx_runtime_core import (
    RUNTIME_COMMAND_NAMES,
    RUNTIME_EVENT_NAMES,
    RUNTIME_SCHEMA_VERSION,
    RuntimeCommand,
    RuntimeEngine,
    runtime_contract_summary,
)


def print_usage() -> None:
    print(
        "usage: omx-runtime <command> [options]\n"
        "\n"
        "commands:\n"
        "  schema [--json]                     print the runtime contract summary\n"
        "  snapshot [--json] [--state-dir=DIR]  print a runtime snapshot\n"
        "  mux-contract                        print the mux boundary summary\n"
        "  exec <json> [--state-dir=DIR]       process a runtime command from JSON\n"
        "  init <state-dir>                    initialize a fresh state directory\n"
    )


def _find_state_dir(args: List[str]) -> Optional[str]:
    for a in args:
        if a.startswith("--state-dir="):
            return a.split("=", 1)[1]
    return None


def run(args: Optional[List[str]] = None) -> None:
    if args is None:
        args = sys.argv[1:]

    first = args[0] if args else None
    second = args[1] if len(args) > 1 else None

    if first in (None, "--help", "-h"):
        print_usage()
        return

    if first == "schema":
        if second == "--json":
            summary = {
                "schema_version": RUNTIME_SCHEMA_VERSION,
                "commands": list(RUNTIME_COMMAND_NAMES),
                "events": list(RUNTIME_EVENT_NAMES),
                "transport": "tmux",
            }
            print(json.dumps(summary, indent=2))
        else:
            print(runtime_contract_summary())
        return

    if first == "snapshot":
        state_dir = _find_state_dir(args)
        if state_dir:
            engine = RuntimeEngine.load(state_dir)
        else:
            engine = RuntimeEngine()
        snapshot = engine.snapshot()
        use_json = "--json" in args
        if use_json:
            from .engine import _snapshot_to_dict
            print(json.dumps(_snapshot_to_dict(snapshot), indent=2))
        else:
            print(snapshot)
        return

    if first == "mux-contract":
        adapter = TmuxAdapter()
        print(f"adapter-status={adapter.status()}")
        print(canonical_contract_summary())
        sample = MuxOperation.inspect_liveness(MuxTarget.detached())
        try:
            adapter.execute(sample)
        except Exception as e:
            print(f"sample-operation={e}")
        return

    if first == "exec":
        if second is None:
            print("exec requires a JSON command argument", file=sys.stderr)
            sys.exit(1)
        state_dir = _find_state_dir(args)
        compact = "--compact" in args

        if state_dir:
            try:
                engine = RuntimeEngine.load(state_dir)
            except Exception:
                engine = RuntimeEngine().with_state_dir(state_dir)
        else:
            engine = RuntimeEngine()

        cmd_data = json.loads(second)
        command = RuntimeCommand(**cmd_data)
        event = engine.process(command)

        if compact:
            engine.compact()
        if state_dir:
            engine.persist()
            engine.write_compatibility_view()

        from .engine import _event_to_dict
        print(json.dumps(_event_to_dict(event), indent=2))
        return

    if first == "init":
        if second is None:
            print("init requires a state directory path", file=sys.stderr)
            sys.exit(1)
        engine = RuntimeEngine().with_state_dir(second)
        engine.persist()
        print(f"initialized state directory: {second}")
        return

    print(f"unknown subcommand `{first}`", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    try:
        run()
    except Exception as e:
        print(f"omx-runtime: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
