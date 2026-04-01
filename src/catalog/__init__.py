"""Catalog manifest module -- schema validation and reader."""

from .reader import (
    PublicCatalogContract,
    get_catalog_counts,
    read_catalog_manifest,
    resolve_manifest_path,
    to_public_catalog_contract,
    try_read_catalog_manifest,
)
from .schema import (
    AgentCategory,
    CatalogAgentEntry,
    CatalogCounts,
    CatalogManifest,
    CatalogManifestError,
    CatalogSkillEntry,
    EntryStatus,
    SkillCategory,
    summarize_catalog_counts,
    validate_catalog_manifest,
)

__all__ = [
    "AgentCategory",
    "CatalogAgentEntry",
    "CatalogCounts",
    "CatalogManifest",
    "CatalogManifestError",
    "CatalogSkillEntry",
    "EntryStatus",
    "PublicCatalogContract",
    "SkillCategory",
    "get_catalog_counts",
    "read_catalog_manifest",
    "resolve_manifest_path",
    "summarize_catalog_counts",
    "to_public_catalog_contract",
    "try_read_catalog_manifest",
    "validate_catalog_manifest",
]
