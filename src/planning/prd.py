"""PRD (Product Requirements Document) model and renderer."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PRDSection:
    """A single section of a PRD."""

    section_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    title: str = ""
    body: str = ""
    order: int = 0
    subsections: list[PRDSection] = field(default_factory=list)

    def add_subsection(self, title: str, body: str = "") -> PRDSection:
        sub = PRDSection(
            title=title,
            body=body,
            order=len(self.subsections),
        )
        self.subsections.append(sub)
        return sub


@dataclass
class PRDDocument:
    """A full Product Requirements Document."""

    doc_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    author: str = ""
    version: str = "0.1.0"
    status: str = "draft"  # draft | review | approved | archived
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    sections: list[PRDSection] = field(default_factory=list)
    stakeholders: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # -- section management ----------------------------------------------------

    def add_section(self, title: str, body: str = "") -> PRDSection:
        section = PRDSection(title=title, body=body, order=len(self.sections))
        self.sections.append(section)
        self.updated_at = time.time()
        return section

    def get_section(self, title: str) -> Optional[PRDSection]:
        for s in self.sections:
            if s.title == title:
                return s
        return None

    def remove_section(self, title: str) -> bool:
        for i, s in enumerate(self.sections):
            if s.title == title:
                self.sections.pop(i)
                self.updated_at = time.time()
                return True
        return False

    def reorder_sections(self, titles: list[str]) -> None:
        by_title = {s.title: s for s in self.sections}
        reordered: list[PRDSection] = []
        for idx, t in enumerate(titles):
            sec = by_title.get(t)
            if sec:
                sec.order = idx
                reordered.append(sec)
        # append any sections not mentioned
        mentioned = set(titles)
        for s in self.sections:
            if s.title not in mentioned:
                s.order = len(reordered)
                reordered.append(s)
        self.sections = reordered
        self.updated_at = time.time()

    # -- validation ------------------------------------------------------------

    def validate(self) -> list[str]:
        """Return a list of validation errors (empty means valid)."""
        errors: list[str] = []
        if not self.title:
            errors.append("PRD must have a title")
        if not self.sections:
            errors.append("PRD must have at least one section")
        required_titles = {"Overview", "Goals", "Requirements"}
        present = {s.title for s in self.sections}
        missing = required_titles - present
        if missing:
            errors.append(f"Missing required sections: {', '.join(sorted(missing))}")
        for s in self.sections:
            if not s.body and not s.subsections:
                errors.append(f"Section '{s.title}' has no body or subsections")
        return errors

    # -- rendering -------------------------------------------------------------

    def render_markdown(self) -> str:
        """Render the full PRD as a Markdown string."""
        lines: list[str] = []
        lines.append(f"# {self.title}")
        lines.append("")
        lines.append(f"**Version:** {self.version}  ")
        lines.append(f"**Status:** {self.status}  ")
        if self.author:
            lines.append(f"**Author:** {self.author}  ")
        if self.stakeholders:
            lines.append(f"**Stakeholders:** {', '.join(self.stakeholders)}  ")
        if self.tags:
            lines.append(f"**Tags:** {', '.join(self.tags)}  ")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Table of contents
        if self.sections:
            lines.append("## Table of Contents")
            lines.append("")
            for i, sec in enumerate(self.sections, 1):
                anchor = sec.title.lower().replace(" ", "-")
                lines.append(f"{i}. [{sec.title}](#{anchor})")
            lines.append("")
            lines.append("---")
            lines.append("")

        for sec in self.sections:
            lines.extend(self._render_section(sec, level=2))

        return "\n".join(lines)

    def _render_section(self, section: PRDSection, level: int) -> list[str]:
        prefix = "#" * level
        lines: list[str] = []
        lines.append(f"{prefix} {section.title}")
        lines.append("")
        if section.body:
            lines.append(section.body)
            lines.append("")
        for sub in section.subsections:
            lines.extend(self._render_section(sub, level + 1))
        return lines
