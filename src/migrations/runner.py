"""Migration runner: executes pending migrations, supports rollback and status."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .registry import BaseMigration, MigrationRegistry, MigrationMeta

logger = logging.getLogger(__name__)


@dataclass
class MigrationResult:
    """Result of a single migration execution."""
    migration_name: str
    from_version: int
    to_version: int
    success: bool
    duration_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class MigrationStatus:
    """Current migration status."""
    current_version: int
    latest_version: int
    pending_count: int
    applied: List[int]
    available: List[MigrationMeta]

    @property
    def is_up_to_date(self) -> bool:
        return self.current_version >= self.latest_version


class MigrationRunner:
    """Executes migrations forward and backward against data dictionaries."""

    def __init__(self, registry: MigrationRegistry):
        self.registry = registry
        self._results: List[MigrationResult] = []

    def run_pending(
        self,
        data: Dict[str, Any],
        current_version: int,
        target_version: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Run all pending migrations from current_version to target (or latest)."""
        target = target_version or self.registry.latest_version

        if current_version >= target:
            logger.info("Already at v%d, no migrations needed", current_version)
            return data

        chain = self.registry.get_chain(current_version, target)
        if not chain:
            logger.warning("No migration chain from v%d to v%d", current_version, target)
            return data

        result_data = dict(data)
        for migration in chain:
            start = time.monotonic()
            try:
                result_data = migration.up(result_data)
                elapsed = (time.monotonic() - start) * 1000

                if not migration.validate(result_data):
                    raise ValueError("Post-migration validation failed")

                self.registry.mark_applied(migration.meta.from_version)
                self._results.append(MigrationResult(
                    migration_name=migration.meta.name,
                    from_version=migration.meta.from_version,
                    to_version=migration.meta.to_version,
                    success=True,
                    duration_ms=elapsed,
                ))
                logger.info(
                    "Applied migration %s (v%d -> v%d) in %.1fms",
                    migration.meta.name,
                    migration.meta.from_version,
                    migration.meta.to_version,
                    elapsed,
                )

            except Exception as e:
                elapsed = (time.monotonic() - start) * 1000
                self._results.append(MigrationResult(
                    migration_name=migration.meta.name,
                    from_version=migration.meta.from_version,
                    to_version=migration.meta.to_version,
                    success=False,
                    duration_ms=elapsed,
                    error=str(e),
                ))
                logger.error("Migration %s failed: %s", migration.meta.name, e)
                break

        return result_data

    def rollback(
        self,
        data: Dict[str, Any],
        current_version: int,
        target_version: int,
    ) -> Dict[str, Any]:
        """Rollback migrations from current_version down to target_version."""
        if current_version <= target_version:
            logger.info("Already at or below v%d", target_version)
            return data

        chain = self.registry.get_rollback_chain(current_version, target_version)
        if not chain:
            logger.warning("No rollback chain from v%d to v%d", current_version, target_version)
            return data

        result_data = dict(data)
        for migration in chain:
            start = time.monotonic()
            try:
                result_data = migration.down(result_data)
                elapsed = (time.monotonic() - start) * 1000

                self._results.append(MigrationResult(
                    migration_name=f"rollback_{migration.meta.name}",
                    from_version=migration.meta.to_version,
                    to_version=migration.meta.from_version,
                    success=True,
                    duration_ms=elapsed,
                ))
                logger.info(
                    "Rolled back %s (v%d -> v%d) in %.1fms",
                    migration.meta.name,
                    migration.meta.to_version,
                    migration.meta.from_version,
                    elapsed,
                )

            except Exception as e:
                elapsed = (time.monotonic() - start) * 1000
                self._results.append(MigrationResult(
                    migration_name=f"rollback_{migration.meta.name}",
                    from_version=migration.meta.to_version,
                    to_version=migration.meta.from_version,
                    success=False,
                    duration_ms=elapsed,
                    error=str(e),
                ))
                logger.error("Rollback of %s failed: %s", migration.meta.name, e)
                break

        return result_data

    def get_status(self, current_version: int) -> MigrationStatus:
        """Get the current migration status."""
        latest = self.registry.latest_version
        available = self.registry.list_all()
        pending = len(self.registry.get_chain(current_version, latest))

        return MigrationStatus(
            current_version=current_version,
            latest_version=latest,
            pending_count=pending,
            applied=self.registry.applied_versions,
            available=available,
        )

    @property
    def results(self) -> List[MigrationResult]:
        return list(self._results)

    def clear_results(self) -> None:
        self._results.clear()
