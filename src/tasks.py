from __future__ import annotations

from .task import WorkspaceTask


def default_tasks() -> list[WorkspaceTask]:
    return [
        WorkspaceTask('root-module-parity', 'Mirror the root module surface of the system configuration'),
        WorkspaceTask('directory-parity', 'Mirror top-level subsystem names as Python packages'),
        WorkspaceTask('config-audit', 'Continuously measure configuration consistency'),
    ]
