"""
Hook Event Dispatcher.

Discovers plugins and dispatches hook events to them, running each plugin
in a subprocess with timeout enforcement.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .loader import (
    discover_hook_plugins,
    is_hook_plugins_enabled,
    resolve_hook_plugin_timeout_ms,
)
from .types import (
    HookDispatchOptions,
    HookDispatchResult,
    HookEventEnvelope,
    HookPluginDispatchResult,
)

RESULT_PREFIX = "__OMX_PLUGIN_RESULT__ "


def _hooks_log_path(cwd: str) -> Path:
    day = datetime.now(timezone.utc).isoformat()[:10]
    return Path(cwd) / ".omx" / "logs" / f"hooks-{day}.jsonl"


async def _append_hooks_log(cwd: str, payload: Dict[str, Any]) -> None:
    log_dir = Path(cwd) / ".omx" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    try:
        entry = {"timestamp": datetime.now(timezone.utc).isoformat(), **payload}
        with open(_hooks_log_path(cwd), "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def _is_team_worker(env: Dict[str, str]) -> bool:
    return bool(env.get("OMX_TEAM_WORKER", "").strip())


async def _run_plugin(
    plugin: dict,
    event: HookEventEnvelope,
    cwd: str,
    timeout_ms: int,
    side_effects_enabled: bool,
    env: Optional[Dict[str, str]] = None,
) -> HookPluginDispatchResult:
    """Run a single plugin in a subprocess with timeout."""
    started = time.monotonic()
    plugin_path = plugin["path"]

    if not Path(plugin_path).exists():
        duration = (time.monotonic() - started) * 1000
        return HookPluginDispatchResult(
            plugin=plugin["id"],
            path=plugin_path,
            file=plugin.get("file"),
            plugin_id=plugin["id"],
            ok=False,
            status="runner_error",
            skipped=True,
            reason="plugin_missing",
            duration_ms=duration,
        )

    # Build a small runner script that imports and calls the plugin
    runner_code = f"""
import sys, json, importlib.util

payload = json.loads(sys.stdin.read())
spec = importlib.util.spec_from_file_location("plugin", payload["pluginPath"])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

handler = getattr(mod, "on_hook_event", None)
if handler is None:
    print("{RESULT_PREFIX}" + json.dumps({{"ok": False, "plugin": payload["pluginId"], "reason": "invalid_export"}}))
    sys.exit(0)

import asyncio
event_data = payload["event"]
result = handler(event_data, None)
if asyncio.iscoroutine(result):
    result = asyncio.get_event_loop().run_until_complete(result)
print("{RESULT_PREFIX}" + json.dumps({{"ok": True, "plugin": payload["pluginId"], "reason": "ok"}}))
"""

    stdin_data = json.dumps({
        "cwd": cwd,
        "pluginId": plugin["id"],
        "pluginPath": plugin_path,
        "event": event.to_dict(),
        "sideEffectsEnabled": side_effects_enabled,
    })

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", runner_code,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env={**os.environ, **(env or {})},
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(input=stdin_data.encode()),
                timeout=timeout_ms / 1000.0,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            duration = (time.monotonic() - started) * 1000
            return HookPluginDispatchResult(
                plugin=plugin["id"],
                path=plugin_path,
                file=plugin.get("file"),
                plugin_id=plugin["id"],
                ok=False,
                status="timeout",
                reason="timeout",
                duration_ms=duration,
            )

        duration = (time.monotonic() - started) * 1000
        stdout = stdout_bytes.decode(errors="replace")
        stderr = stderr_bytes.decode(errors="replace")

        # Parse result from stdout
        lines = [line.strip() for line in stdout.split("\n") if line.strip()]
        raw_result = None
        for line in reversed(lines):
            if line.startswith(RESULT_PREFIX):
                raw_result = line
                break

        parsed = None
        if raw_result:
            try:
                parsed = json.loads(raw_result[len(RESULT_PREFIX):])
            except json.JSONDecodeError:
                pass

        if parsed and parsed.get("ok"):
            return HookPluginDispatchResult(
                plugin=plugin["id"],
                path=plugin_path,
                file=plugin.get("file"),
                plugin_id=plugin["id"],
                ok=True,
                status="ok",
                reason=parsed.get("reason", "ok"),
                duration_ms=duration,
            )

        reason = parsed.get("reason", "plugin_error") if parsed else "plugin_error"
        return HookPluginDispatchResult(
            plugin=plugin["id"],
            path=plugin_path,
            file=plugin.get("file"),
            plugin_id=plugin["id"],
            ok=False,
            status="invalid_export" if reason == "invalid_export" else "error",
            reason=reason,
            error=parsed.get("error") if parsed else (stderr.strip() or None),
            duration_ms=duration,
        )

    except OSError as e:
        duration = (time.monotonic() - started) * 1000
        return HookPluginDispatchResult(
            plugin=plugin["id"],
            path=plugin_path,
            file=plugin.get("file"),
            plugin_id=plugin["id"],
            ok=False,
            status="runner_error",
            reason="spawn_failed",
            error=str(e),
            duration_ms=duration,
        )


def is_hook_plugin_feature_enabled(env: Optional[Dict[str, str]] = None) -> bool:
    """Check if the hook plugin feature is enabled."""
    return is_hook_plugins_enabled(env)


def _should_force_enable_runtime_hook_dispatch(event: HookEventEnvelope) -> bool:
    return event.source in ("native", "derived")


async def dispatch_hook_event(
    event: HookEventEnvelope,
    options: Optional[HookDispatchOptions] = None,
) -> HookDispatchResult:
    """
    Dispatch a hook event to all discovered plugins.

    Discovers plugins in .omx/hooks/, runs each in a subprocess with timeout,
    and collects results.
    """
    if options is None:
        options = HookDispatchOptions()

    cwd = options.cwd or os.getcwd()
    env = options.env or dict(os.environ)

    runtime_dispatch_enabled = (
        _should_force_enable_runtime_hook_dispatch(event)
        or is_hook_plugins_enabled(env)
    )
    enabled = options.enabled if options.enabled is not None else runtime_dispatch_enabled

    summary = HookDispatchResult(
        enabled=enabled,
        reason="ok" if enabled else "disabled",
        event=event.event,
        source=event.source,
        plugin_count=0,
        results=[],
    )

    if not enabled:
        await _append_hooks_log(cwd, {
            "type": "hook_dispatch",
            "event": event.event,
            "source": event.source,
            "enabled": False,
            "reason": "plugins_disabled",
        })
        return summary

    plugins = await discover_hook_plugins(cwd)
    summary.plugin_count = len(plugins)

    in_team_worker = _is_team_worker(env)
    allow_team_side_effects = (
        options.allow_team_worker_side_effects or options.allow_in_team_worker
    )
    side_effects_enabled = (
        options.side_effects_enabled
        if options.side_effects_enabled is not None
        else (not in_team_worker or allow_team_side_effects)
    )

    timeout_ms = options.timeout_ms or resolve_hook_plugin_timeout_ms(env)

    for plugin in plugins:
        plugin_dict = {
            "id": plugin.id,
            "path": plugin.path,
            "file": plugin.file,
        }
        result = await _run_plugin(
            plugin_dict, event, cwd, timeout_ms, side_effects_enabled, env
        )
        summary.results.append(result)

        await _append_hooks_log(cwd, {
            "type": "hook_plugin_dispatch",
            "event": event.event,
            "source": event.source,
            "plugin": plugin.id,
            "file": plugin.file,
            "ok": result.ok,
            "status": result.status,
            "reason": result.reason,
            "error": result.error,
            "duration_ms": result.duration_ms,
        })

    return summary
