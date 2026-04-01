"""Dashboard screen showing agent status, task queue, and metrics."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class AgentStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


STATUS_SYMBOLS = {
    AgentStatus.IDLE: "\u25cb",      # empty circle
    AgentStatus.RUNNING: "\u25cf",   # filled circle
    AgentStatus.PAUSED: "\u25d0",    # half circle
    AgentStatus.ERROR: "\u2717",     # cross
}

STATUS_COLORS = {
    AgentStatus.IDLE: "\033[37m",
    AgentStatus.RUNNING: "\033[32m",
    AgentStatus.PAUSED: "\033[33m",
    AgentStatus.ERROR: "\033[31m",
}

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"


@dataclass
class AgentInfo:
    name: str
    status: AgentStatus = AgentStatus.IDLE
    current_task: Optional[str] = None
    tasks_completed: int = 0
    errors: int = 0


@dataclass
class TaskInfo:
    task_id: str
    description: str
    priority: int = 0
    created_at: Optional[datetime] = None
    assigned_to: Optional[str] = None


@dataclass
class DashboardMetrics:
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    avg_task_duration_seconds: float = 0.0
    tokens_used: int = 0
    api_calls: int = 0


@dataclass
class DashboardData:
    agents: list[AgentInfo] = field(default_factory=list)
    task_queue: list[TaskInfo] = field(default_factory=list)
    metrics: DashboardMetrics = field(default_factory=DashboardMetrics)
    title: str = "orbit Dashboard"


def _box(title: str, content: str, width: int) -> str:
    """Draw a box with a title around content."""
    inner = width - 4
    top = f"\u250c\u2500 {BOLD}{title}{RESET} " + "\u2500" * max(0, inner - len(title) - 1) + "\u2510"
    bot = "\u2514" + "\u2500" * (width - 2) + "\u2518"
    lines = content.split("\n")
    body = "\n".join(
        f"\u2502 {line:<{inner}} \u2502" for line in lines
    )
    return f"{top}\n{body}\n{bot}"


def _render_agents(agents: list[AgentInfo], width: int) -> str:
    """Render agent status section."""
    if not agents:
        return _box("Agents", "  No agents registered", width)
    lines: list[str] = []
    for a in agents:
        sym = STATUS_SYMBOLS[a.status]
        col = STATUS_COLORS[a.status]
        task_str = f" -> {a.current_task}" if a.current_task else ""
        line = f"  {col}{sym}{RESET} {a.name:<16} {a.status.value:<8} done:{a.tasks_completed} err:{a.errors}{task_str}"
        lines.append(line)
    return _box("Agents", "\n".join(lines), width)


def _render_task_queue(tasks: list[TaskInfo], width: int) -> str:
    """Render task queue section."""
    if not tasks:
        return _box("Task Queue", "  Queue is empty", width)
    sorted_tasks = sorted(tasks, key=lambda t: -t.priority)
    lines: list[str] = []
    for i, t in enumerate(sorted_tasks[:10], 1):
        assigned = f" [{t.assigned_to}]" if t.assigned_to else ""
        pri = f"P{t.priority}"
        lines.append(f"  {DIM}{i:>2}.{RESET} {CYAN}{pri}{RESET} {t.description[:40]:<40}{assigned}")
    remaining = len(tasks) - 10
    if remaining > 0:
        lines.append(f"  {DIM}... and {remaining} more{RESET}")
    return _box("Task Queue", "\n".join(lines), width)


def _render_metrics(m: DashboardMetrics, width: int) -> str:
    """Render metrics section."""
    pct = (m.completed_tasks / m.total_tasks * 100) if m.total_tasks else 0
    bar_width = 20
    filled = int(bar_width * pct / 100)
    bar = f"{GREEN}{'█' * filled}{DIM}{'░' * (bar_width - filled)}{RESET}"
    lines = [
        f"  Completion: {bar} {pct:.0f}%",
        f"  Total: {m.total_tasks}  Done: {GREEN}{m.completed_tasks}{RESET}  Failed: {YELLOW}{m.failed_tasks}{RESET}",
        f"  Avg duration: {m.avg_task_duration_seconds:.1f}s",
        f"  Tokens: {m.tokens_used:,}  API calls: {m.api_calls:,}",
    ]
    return _box("Metrics", "\n".join(lines), width)


def render_dashboard(
    data: Optional[DashboardData] = None,
    width: Optional[int] = None,
) -> str:
    """Render the full dashboard screen.

    Args:
        data: Dashboard data to display. Uses empty defaults if None.
        width: Terminal width override.

    Returns:
        Rendered dashboard as a string.
    """
    if data is None:
        data = DashboardData()
    if width is None:
        width = shutil.get_terminal_size((80, 24)).columns

    header = f"\n{BOLD}{data.title.center(width)}{RESET}\n"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ts_line = f"{DIM}{now.center(width)}{RESET}\n"

    parts = [
        header,
        ts_line,
        _render_agents(data.agents, width),
        "",
        _render_task_queue(data.task_queue, width),
        "",
        _render_metrics(data.metrics, width),
        "",
    ]
    return "\n".join(parts)
