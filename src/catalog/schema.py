"""Catalog manifest schema types and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Category / status enums
# ---------------------------------------------------------------------------

class SkillCategory(str, Enum):
    EXECUTION = "execution"
    PLANNING = "planning"
    SHORTCUT = "shortcut"
    UTILITY = "utility"


class AgentCategory(str, Enum):
    BUILD = "build"
    REVIEW = "review"
    DOMAIN = "domain"
    PRODUCT = "product"
    COORDINATION = "coordination"


class EntryStatus(str, Enum):
    ACTIVE = "active"
    ALIAS = "alias"
    MERGED = "merged"
    DEPRECATED = "deprecated"
    INTERNAL = "internal"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CatalogSkillEntry:
    name: str
    category: SkillCategory
    status: EntryStatus
    canonical: str | None = None
    core: bool = False
    internal_required: bool = False


@dataclass(frozen=True)
class CatalogAgentEntry:
    name: str
    category: AgentCategory
    status: EntryStatus
    canonical: str | None = None


@dataclass(frozen=True)
class CatalogManifest:
    schema_version: int
    catalog_version: str
    skills: tuple[CatalogSkillEntry, ...]
    agents: tuple[CatalogAgentEntry, ...]


@dataclass(frozen=True)
class CatalogCounts:
    skill_count: int
    prompt_count: int
    active_skill_count: int
    active_agent_count: int


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_CORE_SKILLS: frozenset[str] = frozenset(
    {"ralplan", "team", "ralph", "ultrawork", "autopilot"}
)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

class CatalogManifestError(ValueError):
    """Raised when manifest validation fails."""

    def __init__(self, tag: str) -> None:
        super().__init__(f"catalog_manifest_invalid:{tag}")
        self.tag = tag


def _assert_non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogManifestError(field)
    return value.strip()


def _validate_skill(entry: Any, index: int) -> CatalogSkillEntry:
    if not isinstance(entry, dict):
        raise CatalogManifestError(f"skills[{index}]")

    name = _assert_non_empty_string(entry.get("name"), f"skills[{index}].name")
    category_str = _assert_non_empty_string(entry.get("category"), f"skills[{index}].category")
    status_str = _assert_non_empty_string(entry.get("status"), f"skills[{index}].status")

    try:
        category = SkillCategory(category_str)
    except ValueError:
        raise CatalogManifestError(f"skills[{index}].category")

    try:
        status = EntryStatus(status_str)
    except ValueError:
        raise CatalogManifestError(f"skills[{index}].status")

    raw_canonical = entry.get("canonical")
    canonical = (
        raw_canonical.strip()
        if isinstance(raw_canonical, str) and raw_canonical.strip()
        else None
    )

    if status in (EntryStatus.ALIAS, EntryStatus.MERGED) and canonical is None:
        raise CatalogManifestError(f"skills[{index}].canonical")

    return CatalogSkillEntry(
        name=name,
        category=category,
        status=status,
        canonical=canonical,
        core=entry.get("core") is True,
        internal_required=entry.get("internalRequired") is True,
    )


def _validate_agent(entry: Any, index: int) -> CatalogAgentEntry:
    if not isinstance(entry, dict):
        raise CatalogManifestError(f"agents[{index}]")

    name = _assert_non_empty_string(entry.get("name"), f"agents[{index}].name")
    category_str = _assert_non_empty_string(entry.get("category"), f"agents[{index}].category")
    status_str = _assert_non_empty_string(entry.get("status"), f"agents[{index}].status")

    try:
        category = AgentCategory(category_str)
    except ValueError:
        raise CatalogManifestError(f"agents[{index}].category")

    try:
        status = EntryStatus(status_str)
    except ValueError:
        raise CatalogManifestError(f"agents[{index}].status")

    raw_canonical = entry.get("canonical")
    canonical = (
        raw_canonical.strip()
        if isinstance(raw_canonical, str) and raw_canonical.strip()
        else None
    )

    if status in (EntryStatus.ALIAS, EntryStatus.MERGED) and canonical is None:
        raise CatalogManifestError(f"agents[{index}].canonical")

    return CatalogAgentEntry(
        name=name,
        category=category,
        status=status,
        canonical=canonical,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_catalog_manifest(data: Any) -> CatalogManifest:
    """Parse and validate raw JSON data into a ``CatalogManifest``."""
    if not isinstance(data, dict):
        raise CatalogManifestError("root")

    schema_version = data.get("schemaVersion")
    if not isinstance(schema_version, int):
        raise CatalogManifestError("schemaVersion")

    catalog_version = _assert_non_empty_string(
        data.get("catalogVersion"), "catalogVersion"
    )

    raw_skills = data.get("skills")
    if not isinstance(raw_skills, list):
        raise CatalogManifestError("skills")

    raw_agents = data.get("agents")
    if not isinstance(raw_agents, list):
        raise CatalogManifestError("agents")

    # Validate skills with dedup
    seen_skills: set[str] = set()
    skills: list[CatalogSkillEntry] = []
    for i, raw in enumerate(raw_skills):
        skill = _validate_skill(raw, i)
        if skill.name in seen_skills:
            raise CatalogManifestError(f"duplicate_skill:{skill.name}")
        seen_skills.add(skill.name)
        skills.append(skill)

    # Validate agents with dedup
    seen_agents: set[str] = set()
    agents: list[CatalogAgentEntry] = []
    for i, raw in enumerate(raw_agents):
        agent = _validate_agent(raw, i)
        if agent.name in seen_agents:
            raise CatalogManifestError(f"duplicate_agent:{agent.name}")
        seen_agents.add(agent.name)
        agents.append(agent)

    # Core skill enforcement
    for core_name in REQUIRED_CORE_SKILLS:
        match = next((s for s in skills if s.name == core_name), None)
        if match is None or match.status != EntryStatus.ACTIVE:
            raise CatalogManifestError(f"missing_core_skill:{core_name}")

    return CatalogManifest(
        schema_version=schema_version,
        catalog_version=catalog_version,
        skills=tuple(skills),
        agents=tuple(agents),
    )


def summarize_catalog_counts(manifest: CatalogManifest) -> CatalogCounts:
    """Return aggregate counts for the manifest."""
    return CatalogCounts(
        skill_count=len(manifest.skills),
        prompt_count=len(manifest.agents),
        active_skill_count=sum(
            1 for s in manifest.skills if s.status == EntryStatus.ACTIVE
        ),
        active_agent_count=sum(
            1 for a in manifest.agents if a.status == EntryStatus.ACTIVE
        ),
    )
