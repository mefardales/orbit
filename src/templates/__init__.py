"""Template loading utilities.

pyclaude stores templates at the repository root ``templates/`` directory
(NOT under ``src/``).  This module provides helpers to discover and render
those templates from Python code.
"""

from __future__ import annotations

from .loader import TemplateStore, discover_templates, load_template

__all__ = [
    'TemplateStore',
    'discover_templates',
    'load_template',
]
