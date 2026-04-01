"""Migration registry with version tracking and discovery."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type

logger = logging.getLogger(__name__)


@dataclass
class MigrationMeta:
    """Metadata about a registered migration."""
    from_version: int
    to_version: int
    name: str
    description: str = ""
    reversible: bool = True


class BaseMigration(ABC):
    """Abstract base class for all migrations."""

    meta: MigrationMeta

    @abstractmethod
    def up(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply the forward migration."""
        ...

    @abstractmethod
    def down(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply the reverse migration (rollback)."""
        ...

    def validate(self, data: Dict[str, Any]) -> bool:
        """Validate data after migration. Override for custom checks."""
        return True


class MigrationRegistry:
    """Central registry that tracks all available migrations and their order."""

    def __init__(self) -> None:
        self._migrations: Dict[int, BaseMigration] = {}  # keyed by from_version
        self._applied: List[int] = []

    def register(self, migration_instance: BaseMigration) -> None:
        """Register a migration. Keyed by its from_version."""
        fv = migration_instance.meta.from_version
        if fv in self._migrations:
            logger.warning(
                "Overwriting migration from v%d (was %s, now %s)",
                fv,
                self._migrations[fv].meta.name,
                migration_instance.meta.name,
            )
        self._migrations[fv] = migration_instance
        logger.debug(
            "Registered migration: %s (v%d -> v%d)",
            migration_instance.meta.name,
            fv,
            migration_instance.meta.to_version,
        )

    def get(self, from_version: int) -> Optional[BaseMigration]:
        """Get the migration for a specific source version."""
        return self._migrations.get(from_version)

    def get_chain(self, from_version: int, to_version: int) -> List[BaseMigration]:
        """Get the ordered list of migrations needed from one version to another."""
        chain: List[BaseMigration] = []
        current = from_version
        while current < to_version:
            m = self._migrations.get(current)
            if m is None:
                logger.error("No migration found from v%d", current)
                break
            chain.append(m)
            current = m.meta.to_version
        return chain

    def get_rollback_chain(self, from_version: int, to_version: int) -> List[BaseMigration]:
        """Get the ordered list of migrations needed to rollback."""
        chain: List[BaseMigration] = []
        current = from_version
        while current > to_version:
            # Find migration that targets current version
            m = None
            for mig in self._migrations.values():
                if mig.meta.to_version == current:
                    m = mig
                    break
            if m is None or not m.meta.reversible:
                logger.error("Cannot rollback to v%d from v%d", to_version, current)
                break
            chain.append(m)
            current = m.meta.from_version
        return chain

    def list_all(self) -> List[MigrationMeta]:
        """Return metadata for all registered migrations, sorted by version."""
        return sorted(
            [m.meta for m in self._migrations.values()],
            key=lambda m: m.from_version,
        )

    def mark_applied(self, version: int) -> None:
        """Mark a version as having been applied."""
        if version not in self._applied:
            self._applied.append(version)

    @property
    def applied_versions(self) -> List[int]:
        return sorted(self._applied)

    @property
    def latest_version(self) -> int:
        if not self._migrations:
            return 0
        return max(m.meta.to_version for m in self._migrations.values())

    @property
    def count(self) -> int:
        return len(self._migrations)


# Module-level default registry
_default_registry = MigrationRegistry()


def migration(
    from_version: int,
    to_version: int,
    name: str = "",
    description: str = "",
    reversible: bool = True,
) -> Callable[[Type[BaseMigration]], Type[BaseMigration]]:
    """Decorator to register a migration class with the default registry."""

    def decorator(cls: Type[BaseMigration]) -> Type[BaseMigration]:
        cls.meta = MigrationMeta(
            from_version=from_version,
            to_version=to_version,
            name=name or cls.__name__,
            description=description,
            reversible=reversible,
        )
        _default_registry.register(cls())
        return cls

    return decorator


def get_default_registry() -> MigrationRegistry:
    """Return the module-level default registry."""
    return _default_registry
