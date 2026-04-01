"""
Execution Trace / Timeline MCP Server.

Reads .omx/logs/ turn JSONL files and mode state files to produce
chronological agent flow timelines and aggregate summaries.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Generator, List, Optional

from .bootstrap import (
    McpServer,
    ToolDefinition,
    ToolResult,
    auto_start_stdio_mcp_server,
    error_result,
    text_result,
)
from .state_paths import (
    list_mode_state_files_with_scope_preference,
    resolve_working_directory_for_state,
)

# ── Types ────────────────────────────────────────────────────────────────────


@dataclass
class TraceEntry:
    timestamp: str = ""
    type: str = ""
    thread_id: Optional[str] = None
    turn_id: Optional[str] = None
    input_preview: Optional[str] = None
    output_preview: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TraceEntry":
        return cls(
            timestamp=d.get("timestamp", ""),
            type=d.get("type", ""),
            thread_id=d.get("thread_id"),
            turn_id=d.get("turn_id"),
            input_preview=d.get("input_preview"),
            output_preview=d.get("output_preview"),
        )


@dataclass
class ModeEvent:
    timestamp: str
    event: str
    mode: str
    details: Optional[Dict[str, Any]] = None


@dataclass
class LogSummary:
    total_turns: int = 0
    turns_by_type: Dict[str, int] = field(default_factory=dict)
    first_timestamp: Optional[str] = None
    last_timestamp: Optional[str] = None


@dataclass
class Metrics:
    total_turns: int = 0
    session_turns: int = 0
    last_activity: str = ""
    session_input_tokens: Optional[int] = None
    session_output_tokens: Optional[int] = None
    session_total_tokens: Optional[int] = None


# ── Log file reading ─────────────────────────────────────────────────────────


def _iterate_log_entries(logs_dir: Path) -> Generator[TraceEntry, None, None]:
    """Yield TraceEntry objects from turns-*.jsonl files in chronological file order."""
    if not logs_dir.exists():
        return

    files = sorted(
        f for f in logs_dir.iterdir()
        if f.name.startswith("turns-") and f.name.endswith(".jsonl")
    )

    for file in files:
        try:
            for line in file.read_text("utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    yield TraceEntry.from_dict(json.loads(line))
                except json.JSONDecodeError:
                    pass
        except OSError:
            pass


def _keep_last_entries(entries: List[TraceEntry], entry: TraceEntry, limit: int) -> None:
    """Maintain a sorted list of the last N entries by timestamp (min-heap style)."""
    if limit <= 0:
        return

    if len(entries) < limit:
        entries.append(entry)
        entries.sort(key=lambda e: e.timestamp or "")
        return

    # If new entry is older than the oldest kept, skip
    if (entry.timestamp or "") <= (entries[0].timestamp or ""):
        return

    # Replace the oldest entry and re-sort
    entries[0] = entry
    i = 0
    while i + 1 < len(entries) and (entries[i].timestamp or "") > (entries[i + 1].timestamp or ""):
        entries[i], entries[i + 1] = entries[i + 1], entries[i]
        i += 1


def read_log_files(logs_dir: Path, last: Optional[int] = None) -> List[TraceEntry]:
    """Read trace entries from log files.

    If *last* is given, returns only the last N entries (by timestamp).
    """
    if last and last > 0:
        entries: List[TraceEntry] = []
        for entry in _iterate_log_entries(logs_dir):
            _keep_last_entries(entries, entry, last)
        return entries

    entries = list(_iterate_log_entries(logs_dir))
    entries.sort(key=lambda e: e.timestamp or "")
    return entries


def summarize_log_files(logs_dir: Path) -> LogSummary:
    """Compute aggregate statistics over all log entries."""
    summary = LogSummary()

    for turn in _iterate_log_entries(logs_dir):
        summary.total_turns += 1
        turn_type = turn.type or "unknown"
        summary.turns_by_type[turn_type] = summary.turns_by_type.get(turn_type, 0) + 1

        ts = turn.timestamp or ""
        if not ts:
            continue
        if summary.first_timestamp is None or ts < summary.first_timestamp:
            summary.first_timestamp = ts
        if summary.last_timestamp is None or ts > summary.last_timestamp:
            summary.last_timestamp = ts

    return summary


# ── Mode events ──────────────────────────────────────────────────────────────


def read_mode_events(working_directory: str) -> List[ModeEvent]:
    """Read mode start/end events from state files."""
    events: List[ModeEvent] = []
    refs = list_mode_state_files_with_scope_preference(working_directory)

    for ref in refs:
        try:
            data = json.loads(Path(ref.path).read_text("utf-8"))
            if data.get("started_at"):
                events.append(ModeEvent(
                    timestamp=data["started_at"],
                    event="mode_start",
                    mode=ref.mode,
                    details={
                        "phase": data.get("current_phase"),
                        "active": data.get("active"),
                        "scope": ref.scope,
                        "path": ref.path,
                    },
                ))
            if data.get("completed_at"):
                events.append(ModeEvent(
                    timestamp=data["completed_at"],
                    event="mode_end",
                    mode=ref.mode,
                    details={
                        "phase": data.get("current_phase"),
                        "scope": ref.scope,
                        "path": ref.path,
                    },
                ))
        except (json.JSONDecodeError, OSError):
            pass

    events.sort(key=lambda e: e.timestamp)
    return events


# ── Metrics ──────────────────────────────────────────────────────────────────


def read_metrics(omx_dir: Path) -> Optional[Dict[str, Any]]:
    metrics_path = omx_dir / "metrics.json"
    if not metrics_path.exists():
        return None
    try:
        return json.loads(metrics_path.read_text("utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ── MCP Server ───────────────────────────────────────────────────────────────


class TraceServer:
    """MCP server providing trace timeline and summary tools."""

    async def list_tools(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name="trace_timeline",
                description="Show chronological agent flow trace timeline with turns and mode transitions.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "last": {"type": "number", "description": "Show only the last N entries"},
                        "filter": {
                            "type": "string",
                            "enum": ["all", "turns", "modes"],
                            "description": "Filter: all (default), turns only, or modes only",
                        },
                        "workingDirectory": {"type": "string"},
                    },
                },
            ),
            ToolDefinition(
                name="trace_summary",
                description="Show aggregate statistics: turn counts, mode usage, token consumption, and timing.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "workingDirectory": {"type": "string"},
                    },
                },
            ),
        ]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        a = arguments or {}
        try:
            wd = resolve_working_directory_for_state(a.get("workingDirectory"))
        except ValueError as e:
            return error_result(str(e))

        omx_dir = Path(wd) / ".omx"
        logs_dir = omx_dir / "logs"

        if name == "trace_timeline":
            last = a.get("last")
            filter_mode = a.get("filter", "all")

            turns: List[TraceEntry] = []
            mode_events: List[ModeEvent] = []

            if filter_mode != "modes":
                turns = read_log_files(logs_dir, last)
            if filter_mode != "turns":
                mode_events = read_mode_events(wd)

            # Build unified timeline
            timeline: List[Dict[str, Any]] = []
            for t in turns:
                timeline.append({
                    "timestamp": t.timestamp,
                    "type": "turn",
                    "turn_type": t.type,
                    "thread_id": t.thread_id,
                    "input_preview": t.input_preview,
                    "output_preview": t.output_preview,
                })
            for e in mode_events:
                entry: Dict[str, Any] = {
                    "timestamp": e.timestamp,
                    "type": e.event,
                    "mode": e.mode,
                }
                if e.details:
                    entry.update(e.details)
                timeline.append(entry)

            timeline.sort(key=lambda x: x.get("timestamp", ""))
            result = timeline[-last:] if last else timeline

            return text_result({
                "entryCount": len(result),
                "totalAvailable": len(timeline),
                "filter": filter_mode,
                "timeline": result,
            })

        elif name == "trace_summary":
            log_summary = summarize_log_files(logs_dir)
            mode_events = read_mode_events(wd)
            metrics = read_metrics(omx_dir)

            modes_by_name: Dict[str, Dict[str, int]] = {}
            for e in mode_events:
                if e.mode not in modes_by_name:
                    modes_by_name[e.mode] = {"starts": 0, "ends": 0}
                if e.event == "mode_start":
                    modes_by_name[e.mode]["starts"] += 1
                if e.event == "mode_end":
                    modes_by_name[e.mode]["ends"] += 1

            duration_ms = 0
            if log_summary.first_timestamp and log_summary.last_timestamp:
                try:
                    first = datetime.fromisoformat(log_summary.first_timestamp.rstrip("Z") + "+00:00")
                    last_ts = datetime.fromisoformat(log_summary.last_timestamp.rstrip("Z") + "+00:00")
                    duration_ms = int((last_ts - first).total_seconds() * 1000)
                except ValueError:
                    pass

            duration_formatted = "N/A"
            if duration_ms > 0:
                mins = duration_ms // 60000
                secs = (duration_ms % 60000) // 1000
                duration_formatted = f"{mins}m {secs}s"

            return text_result({
                "turns": {
                    "total": log_summary.total_turns,
                    "byType": log_summary.turns_by_type,
                    "firstAt": log_summary.first_timestamp,
                    "lastAt": log_summary.last_timestamp,
                    "durationMs": duration_ms,
                    "durationFormatted": duration_formatted,
                },
                "modes": modes_by_name,
                "metrics": metrics or {"note": "No metrics file found"},
            })

        return error_result(f"Unknown tool: {name}")

    async def close(self) -> None:
        pass


def main() -> None:
    auto_start_stdio_mcp_server("trace", TraceServer())


if __name__ == "__main__":
    main()
