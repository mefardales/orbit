"""Buddy - AI pair programming assistant."""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .context import BuddyContext, BuddyPreferences


@dataclass
class Suggestion:
    """A code suggestion from the buddy."""

    original: str
    suggested: str
    explanation: str
    confidence: float = 0.0  # 0.0 - 1.0
    category: str = "general"  # "refactor", "bug", "style", "performance"


@dataclass
class ReviewComment:
    """A review comment on a code snippet."""

    line: int
    severity: str  # "info", "warning", "error"
    message: str
    suggestion: Optional[str] = None


class Buddy:
    """AI pair programming buddy that provides suggestions, explanations, and reviews."""

    def __init__(self, context: Optional[BuddyContext] = None) -> None:
        self.context = context or BuddyContext()
        self._suggestion_history: list[Suggestion] = []

    def suggest(self, code: str, intent: str = "") -> Suggestion:
        """Generate a code improvement suggestion.

        Args:
            code: The code snippet to improve.
            intent: Optional description of what the user wants.

        Returns:
            A Suggestion with the improved code and explanation.
        """
        self.context.add_message("user", f"Suggest improvement for: {code[:80]}")
        suggested = code
        explanation_parts: list[str] = []

        # Pattern-based suggestions
        if "except:" in code or "except Exception:" in code:
            suggested = re.sub(
                r"except\s*(Exception)?:",
                "except Exception as e:  # noqa: BLE001",
                suggested,
            )
            explanation_parts.append("Catch specific exceptions and bind to a variable for logging.")

        if re.search(r"print\(", code) and "def " in code:
            suggested = re.sub(
                r'\bprint\((.*?)\)',
                r'logger.debug(\1)',
                suggested,
            )
            explanation_parts.append("Replace print() with structured logging in function bodies.")

        # Detect mutable default arguments
        mutable_default = re.search(r'def\s+\w+\([^)]*=\s*(\[\]|\{\}|\bset\(\))', code)
        if mutable_default:
            explanation_parts.append(
                "Mutable default argument detected. Use None as default and initialize inside the function."
            )
            suggested = re.sub(
                r'(def\s+\w+\([^)]*\w+)\s*=\s*(\[\]|\{\})',
                r'\1=None',
                suggested,
            )

        if not explanation_parts:
            explanation_parts.append("Code looks reasonable. No immediate improvements detected.")

        explanation = " ".join(explanation_parts)
        suggestion = Suggestion(
            original=code,
            suggested=suggested,
            explanation=explanation,
            confidence=0.7 if suggested != code else 0.3,
            category="refactor" if suggested != code else "general",
        )
        self._suggestion_history.append(suggestion)
        self.context.add_message("assistant", explanation)
        return suggestion

    def explain(self, code: str) -> str:
        """Explain what a code snippet does.

        Args:
            code: The code to explain.

        Returns:
            A human-readable explanation string.
        """
        self.context.add_message("user", f"Explain: {code[:80]}")
        lines = code.strip().splitlines()
        explanations: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("def "):
                match = re.match(r'def\s+(\w+)\(([^)]*)\)', stripped)
                if match:
                    name, params = match.group(1), match.group(2)
                    param_list = [p.strip().split(":")[0].split("=")[0].strip() for p in params.split(",") if p.strip()]
                    explanations.append(f"Defines function '{name}' with parameters: {', '.join(param_list) or 'none'}")
            elif stripped.startswith("class "):
                match = re.match(r'class\s+(\w+)', stripped)
                if match:
                    explanations.append(f"Defines class '{match.group(1)}'")
            elif stripped.startswith("import ") or stripped.startswith("from "):
                explanations.append(f"Imports: {stripped}")
            elif "return " in stripped:
                explanations.append(f"Returns a value: {stripped}")
            elif re.match(r'for\s+\w+\s+in\s+', stripped):
                explanations.append(f"Loop: {stripped}")
            elif stripped.startswith("if ") or stripped.startswith("elif "):
                explanations.append(f"Conditional: {stripped}")

        if not explanations:
            explanations.append(f"Code block with {len(lines)} line(s).")

        result = "\n".join(f"  - {e}" for e in explanations)
        self.context.add_message("assistant", result)
        return result

    def refactor(self, code: str, goal: str = "clean up") -> Suggestion:
        """Suggest a refactored version of the code.

        Args:
            code: Code to refactor.
            goal: Refactoring goal description.

        Returns:
            Suggestion with refactored code.
        """
        self.context.add_message("user", f"Refactor ({goal}): {code[:80]}")
        refactored = code

        # Remove trailing whitespace
        refactored = "\n".join(line.rstrip() for line in refactored.splitlines())

        # Simplify boolean returns
        refactored = re.sub(
            r'if\s+(.+?):\s*\n\s*return\s+True\s*\n\s*(?:else:\s*\n\s*)?return\s+False',
            r'return \1',
            refactored,
        )

        # Use f-strings instead of .format()
        refactored = re.sub(
            r'"([^"]*?)\{(\w+)\}([^"]*?)"\.format\((\w+=\w+(?:,\s*\w+=\w+)*)\)',
            lambda m: f'f"{m.group(1)}{{{m.group(2)}}}{m.group(3)}"',
            refactored,
        )

        explanation = f"Refactored with goal: {goal}. Applied whitespace cleanup and pattern simplification."
        suggestion = Suggestion(
            original=code,
            suggested=refactored,
            explanation=explanation,
            confidence=0.6,
            category="refactor",
        )
        self.context.add_message("assistant", explanation)
        return suggestion

    def review_snippet(self, code: str) -> list[ReviewComment]:
        """Review a code snippet and return comments.

        Args:
            code: Code to review.

        Returns:
            List of review comments with line numbers.
        """
        self.context.add_message("user", f"Review: {code[:80]}")
        comments: list[ReviewComment] = []
        lines = code.splitlines()

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # Check line length
            if len(line) > 120:
                comments.append(ReviewComment(i, "warning", f"Line too long ({len(line)} chars)", "Break into multiple lines"))
            # Bare except
            if stripped == "except:":
                comments.append(ReviewComment(i, "error", "Bare except catches all exceptions including KeyboardInterrupt", "Use 'except Exception as e:'"))
            # TODO/FIXME/HACK
            if re.search(r'\b(TODO|FIXME|HACK|XXX)\b', stripped):
                comments.append(ReviewComment(i, "info", f"Found annotation: {stripped.strip()}"))
            # Hardcoded credentials pattern
            if re.search(r'(password|secret|api_key|token)\s*=\s*["\']', stripped, re.IGNORECASE):
                comments.append(ReviewComment(i, "error", "Possible hardcoded credential", "Use environment variables or a secrets manager"))
            # Wildcard import
            if stripped.startswith("from ") and "import *" in stripped:
                comments.append(ReviewComment(i, "warning", "Wildcard import pollutes namespace", "Import specific names"))
            # Mutable default
            if re.search(r'def\s+\w+\([^)]*=\s*(\[\]|\{\})', stripped):
                comments.append(ReviewComment(i, "error", "Mutable default argument", "Use None and initialize in function body"))

        summary = f"Reviewed {len(lines)} lines, found {len(comments)} issue(s)."
        self.context.add_message("assistant", summary)
        return comments

    @property
    def history(self) -> list[Suggestion]:
        """Past suggestions."""
        return list(self._suggestion_history)
