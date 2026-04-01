"""Template discovery and rendering.

Templates are plain-text files (Markdown or otherwise) that live under
a ``templates/`` directory at the project root.  Each file is identified
by its stem (filename without extension).

A lightweight ``string.Template``-style substitution is supported via
``$variable`` placeholders.
"""

from __future__ import annotations

import string
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


def _default_template_dir() -> Path:
    """Walk up from this file to find a ``templates/`` directory."""
    current = Path(__file__).resolve().parent
    for _ in range(5):
        candidate = current / 'templates'
        if candidate.is_dir():
            return candidate
        current = current.parent
    # Fallback: repo root relative to src/templates/loader.py
    return Path(__file__).resolve().parents[2] / 'templates'


@dataclass(frozen=True)
class Template:
    """A single loaded template."""
    name: str
    path: Path
    raw: str

    def render(self, variables: Mapping[str, str] | None = None) -> str:
        """Return the template text with ``$key`` placeholders substituted."""
        if not variables:
            return self.raw
        return string.Template(self.raw).safe_substitute(variables)


@dataclass
class TemplateStore:
    """In-memory collection of discovered templates."""
    templates: dict[str, Template] = field(default_factory=dict)

    def get(self, name: str) -> Template | None:
        return self.templates.get(name)

    def names(self) -> list[str]:
        return sorted(self.templates)

    def __len__(self) -> int:
        return len(self.templates)


def discover_templates(root: Path | None = None) -> TemplateStore:
    """Scan *root* for template files and return a populated store.

    Recognised extensions: ``.md``, ``.txt``, ``.tmpl``.
    """
    root = root or _default_template_dir()
    store = TemplateStore()
    if not root.is_dir():
        return store

    extensions = {'.md', '.txt', '.tmpl'}
    for path in sorted(root.iterdir()):
        if path.is_file() and path.suffix in extensions:
            name = path.stem
            store.templates[name] = Template(
                name=name,
                path=path,
                raw=path.read_text(encoding='utf-8'),
            )
    return store


def load_template(name: str, root: Path | None = None) -> Template | None:
    """Convenience: load a single template by name."""
    return discover_templates(root).get(name)
