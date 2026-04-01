from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkspaceContext:
    source_root: Path
    tests_root: Path
    assets_root: Path
    config_root: Path
    python_file_count: int
    test_file_count: int
    asset_file_count: int
    config_available: bool


def build_workspace_context(base: Path | None = None) -> WorkspaceContext:
    root = base or Path(__file__).resolve().parent.parent
    source_root = root / 'src'
    tests_root = root / 'tests'
    assets_root = root / 'assets'
    config_root = root / 'archive' / 'claude_code_ts_snapshot' / 'src'
    return WorkspaceContext(
        source_root=source_root,
        tests_root=tests_root,
        assets_root=assets_root,
        config_root=config_root,
        python_file_count=sum(1 for path in source_root.rglob('*.py') if path.is_file()),
        test_file_count=sum(1 for path in tests_root.rglob('*.py') if path.is_file()),
        asset_file_count=sum(1 for path in assets_root.rglob('*') if path.is_file()),
        config_available=config_root.exists(),
    )


def render_context(context: WorkspaceContext) -> str:
    return '\n'.join([
        f'Source root: {context.source_root}',
        f'Test root: {context.tests_root}',
        f'Assets root: {context.assets_root}',
        f'Archive root: {context.config_root}',
        f'Python files: {context.python_file_count}',
        f'Test files: {context.test_file_count}',
        f'Assets: {context.asset_file_count}',
        f'Archive available: {context.config_available}',
    ])
