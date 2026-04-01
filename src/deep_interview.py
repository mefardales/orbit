"""
DeepInterviewer: Guided interactive parameter collection for mission templates.

Parses a markdown template that contains ``{{ PARAM_NAME }}`` (or
``{{ PARAM_NAME: type }}`` / ``{{ PARAM_NAME: type | description }}``)
placeholders, presents Q&A prompts to the user via Rich console, validates
responses, and produces a filled mission document.

Supported parameter types:
    string  — any non-empty text (default)
    int     — integer (optionally bounded: ``int:min,max``)
    float   — floating-point number
    bool    — yes/no question
    choice  — pick from a list (``choice:opt1,opt2,...``)
    path    — filesystem path (validated for existence when prefixed ``exists:``)

Template placeholder syntax
----------------------------
    {{ NAME }}                          — string, no description
    {{ NAME: string }}                  — explicit string type
    {{ NAME: int }}                     — integer
    {{ NAME: int:1,100 }}               — integer in range [1, 100]
    {{ NAME: choice:small,medium,large }} — enumerated choice
    {{ NAME: path }}                    — filesystem path
    {{ NAME: path:exists }}             — path that must already exist
    {{ NAME: bool }}                    — yes/no boolean
    {{ NAME: string | Short description shown to the user }}
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

# Rich is declared as a project dependency (pyproject.toml).
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm, Prompt
    from rich.table import Table
    from rich import print as rprint
    _RICH_AVAILABLE = True
except ImportError:  # pragma: no cover
    _RICH_AVAILABLE = False


# ---------------------------------------------------------------------------
# Parameter descriptor
# ---------------------------------------------------------------------------


@dataclass
class ParameterSpec:
    """Describes a single template parameter."""

    name: str
    raw_type: str = "string"          # raw type token from the template
    kind: str = "string"              # normalised kind: string|int|float|bool|choice|path
    description: str = ""
    choices: list[str] = field(default_factory=list)
    int_min: Optional[int] = None
    int_max: Optional[int] = None
    path_must_exist: bool = False


@dataclass
class CollectedParameter:
    """A parameter value collected during the interview."""

    name: str
    raw_input: str
    value: Any                        # coerced Python value


# ---------------------------------------------------------------------------
# Template parsing
# ---------------------------------------------------------------------------

# Matches {{ NAME }}, {{ NAME: type }}, {{ NAME: type | description }}
# Allows spaces around the colon and pipe.
_PLACEHOLDER_RE = re.compile(
    r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)"   # name
    r"(?:\s*:\s*([^|}]+?))??"              # optional type spec
    r"(?:\s*\|\s*([^}]+?))?"              # optional description
    r"\s*\}\}",
    re.DOTALL,
)


def _parse_kind(type_token: str) -> tuple[str, list[str], Optional[int], Optional[int], bool]:
    """
    Parse a type token like ``int:1,100`` or ``choice:a,b,c`` or ``path:exists``.

    Returns:
        (kind, choices, int_min, int_max, path_must_exist)
    """
    token = type_token.strip().lower()

    if token in ("string", "str", "text", ""):
        return "string", [], None, None, False

    if token in ("bool", "boolean", "yes/no"):
        return "bool", [], None, None, False

    if token in ("float", "number", "num"):
        return "float", [], None, None, False

    if token.startswith("int"):
        kind = "int"
        rest = token[3:].lstrip(":").strip()
        int_min: Optional[int] = None
        int_max: Optional[int] = None
        if rest:
            parts = [p.strip() for p in rest.split(",")]
            if len(parts) >= 1 and parts[0]:
                try:
                    int_min = int(parts[0])
                except ValueError:
                    pass
            if len(parts) >= 2 and parts[1]:
                try:
                    int_max = int(parts[1])
                except ValueError:
                    pass
        return kind, [], int_min, int_max, False

    if token.startswith("choice"):
        rest = token[6:].lstrip(":").strip()
        choices = [c.strip() for c in rest.split(",") if c.strip()] if rest else []
        return "choice", choices, None, None, False

    if token.startswith("path"):
        rest = token[4:].lstrip(":").strip()
        must_exist = "exist" in rest
        return "path", [], None, None, must_exist

    # Unknown — treat as string.
    return "string", [], None, None, False


def parse_template_parameters(template: str) -> list[ParameterSpec]:
    """
    Extract all unique ``{{ NAME }}`` placeholders from *template*.

    Preserves first-seen order.  If the same name appears multiple times with
    different type annotations, the first annotation wins.

    Args:
        template: Raw template string containing ``{{ }}`` placeholders.

    Returns:
        Ordered list of :class:`ParameterSpec` objects.
    """
    seen: dict[str, ParameterSpec] = {}
    for match in _PLACEHOLDER_RE.finditer(template):
        name = match.group(1)
        type_raw = (match.group(2) or "").strip()
        description = (match.group(3) or "").strip()

        if name in seen:
            continue

        kind, choices, int_min, int_max, path_must_exist = _parse_kind(type_raw)
        seen[name] = ParameterSpec(
            name=name,
            raw_type=type_raw,
            kind=kind,
            description=description,
            choices=choices,
            int_min=int_min,
            int_max=int_max,
            path_must_exist=path_must_exist,
        )
    return list(seen.values())


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


class ValidationError(Exception):
    """Raised when a user's input does not satisfy the parameter spec."""


def validate_and_coerce(raw: str, spec: ParameterSpec) -> Any:
    """
    Validate *raw* input against *spec* and return the coerced Python value.

    Raises:
        ValidationError: with a human-readable message if validation fails.
    """
    stripped = raw.strip()

    if spec.kind == "string":
        if not stripped:
            raise ValidationError("Value must not be empty.")
        return stripped

    if spec.kind == "bool":
        lowered = stripped.lower()
        if lowered in ("y", "yes", "true", "1", "on"):
            return True
        if lowered in ("n", "no", "false", "0", "off"):
            return False
        raise ValidationError("Enter yes/no (y/n).")

    if spec.kind == "int":
        try:
            value = int(stripped)
        except ValueError:
            raise ValidationError(f"'{stripped}' is not a valid integer.")
        if spec.int_min is not None and value < spec.int_min:
            raise ValidationError(f"Value must be >= {spec.int_min}.")
        if spec.int_max is not None and value > spec.int_max:
            raise ValidationError(f"Value must be <= {spec.int_max}.")
        return value

    if spec.kind == "float":
        try:
            return float(stripped)
        except ValueError:
            raise ValidationError(f"'{stripped}' is not a valid number.")

    if spec.kind == "choice":
        if not spec.choices:
            return stripped  # no constraint
        lowered = stripped.lower()
        for choice in spec.choices:
            if choice.lower() == lowered:
                return choice
        raise ValidationError(
            f"'{stripped}' is not a valid choice. Options: {', '.join(spec.choices)}"
        )

    if spec.kind == "path":
        p = Path(stripped).expanduser()
        if spec.path_must_exist and not p.exists():
            raise ValidationError(f"Path does not exist: {p}")
        return str(p)

    # Fallback.
    return stripped


# ---------------------------------------------------------------------------
# Rich console Q&A
# ---------------------------------------------------------------------------


def _build_prompt_text(spec: ParameterSpec, index: int, total: int) -> str:
    parts = [f"[bold cyan]({index}/{total})[/bold cyan] [bold]{spec.name}[/bold]"]
    if spec.description:
        parts.append(f"  [dim]{spec.description}[/dim]")
    if spec.kind == "int":
        if spec.int_min is not None and spec.int_max is not None:
            parts.append(f"  [yellow]integer [{spec.int_min}–{spec.int_max}][/yellow]")
        elif spec.int_min is not None:
            parts.append(f"  [yellow]integer >= {spec.int_min}[/yellow]")
        elif spec.int_max is not None:
            parts.append(f"  [yellow]integer <= {spec.int_max}[/yellow]")
        else:
            parts.append("  [yellow]integer[/yellow]")
    elif spec.kind == "float":
        parts.append("  [yellow]number[/yellow]")
    elif spec.kind == "choice":
        parts.append(f"  [yellow]choices: {', '.join(spec.choices)}[/yellow]")
    elif spec.kind == "bool":
        parts.append("  [yellow]yes/no[/yellow]")
    elif spec.kind == "path":
        suffix = " (must exist)" if spec.path_must_exist else ""
        parts.append(f"  [yellow]path{suffix}[/yellow]")
    return "\n".join(parts)


def _ask_one_rich(console: "Console", spec: ParameterSpec, index: int, total: int) -> CollectedParameter:
    """Ask a single question using Rich, retry on validation error."""
    prompt_markup = _build_prompt_text(spec, index, total)
    while True:
        console.print(prompt_markup)
        if spec.kind == "bool":
            try:
                confirm = Confirm.ask("  Answer", console=console)
                raw = "yes" if confirm else "no"
            except (KeyboardInterrupt, EOFError):
                raise KeyboardInterrupt
        elif spec.kind == "choice" and spec.choices:
            choice_str = "/".join(spec.choices)
            try:
                raw = Prompt.ask(f"  Choose [{choice_str}]", console=console, choices=spec.choices)
            except (KeyboardInterrupt, EOFError):
                raise KeyboardInterrupt
        else:
            try:
                raw = Prompt.ask("  Answer", console=console)
            except (KeyboardInterrupt, EOFError):
                raise KeyboardInterrupt

        try:
            coerced = validate_and_coerce(raw, spec)
            console.print(f"  [green]✓[/green] [dim]{coerced}[/dim]\n")
            return CollectedParameter(name=spec.name, raw_input=raw, value=coerced)
        except ValidationError as exc:
            console.print(f"  [red]✗ {exc}[/red]  Please try again.\n")


def _ask_one_plain(spec: ParameterSpec, index: int, total: int) -> CollectedParameter:
    """Fallback Q&A without Rich."""
    kind_hint = ""
    if spec.kind != "string":
        kind_hint = f" [{spec.kind}]"
    if spec.kind == "choice" and spec.choices:
        kind_hint = f" ({'/'.join(spec.choices)})"
    desc = f" — {spec.description}" if spec.description else ""

    while True:
        line = f"({index}/{total}) {spec.name}{desc}{kind_hint}: "
        try:
            raw = input(line).strip()
        except (KeyboardInterrupt, EOFError):
            raise KeyboardInterrupt
        try:
            coerced = validate_and_coerce(raw, spec)
            return CollectedParameter(name=spec.name, raw_input=raw, value=coerced)
        except ValidationError as exc:
            print(f"  Error: {exc}  Please try again.")


# ---------------------------------------------------------------------------
# Template filling
# ---------------------------------------------------------------------------


def fill_template(template: str, params: dict[str, Any]) -> str:
    """
    Replace all ``{{ NAME }}`` (and typed variants) in *template* with their
    collected values from *params*.

    Args:
        template: Raw template string.
        params: Mapping of parameter name → coerced Python value.

    Returns:
        Filled template string.
    """
    def replacer(match: re.Match) -> str:  # type: ignore[type-arg]
        name = match.group(1)
        if name in params:
            return str(params[name])
        return match.group(0)  # leave unresolved placeholders as-is

    return _PLACEHOLDER_RE.sub(replacer, template)


# ---------------------------------------------------------------------------
# DeepInterviewer
# ---------------------------------------------------------------------------


class DeepInterviewer:
    """
    Guided interactive parameter collection for mission templates.

    Workflow::

        interviewer = DeepInterviewer()
        interviewer.start("/path/to/mission-template.md")
        # user answers questions interactively
        params = interviewer.get_parameters()
        filled_doc = interviewer.generate_mission()
        # optionally save:
        interviewer.save_mission("/path/to/output.md")

    All collected state is held in-process.  To persist, call save_mission().
    """

    def __init__(self, console: Optional["Console"] = None) -> None:
        """
        Args:
            console: Optional Rich Console instance. If None, one is created
                     automatically when Rich is available; otherwise plain
                     stdin/stdout is used.
        """
        self._console: Optional["Console"] = console
        self._template_path: Optional[str] = None
        self._template: Optional[str] = None
        self._specs: list[ParameterSpec] = []
        self._collected: list[CollectedParameter] = []
        self._params: dict[str, Any] = {}
        self._interview_complete: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, template_path: str, *, skip_missing_ok: bool = False) -> list[ParameterSpec]:
        """
        Load a mission template and run the interactive Q&A interview.

        After this method returns (or after the user answers all questions),
        the collected parameters are accessible via get_parameters() and
        generate_mission().

        Args:
            template_path: Path to the markdown mission template.  The file
                           must exist.
            skip_missing_ok: If True, silently continue when the template
                             contains no placeholders.

        Returns:
            List of ParameterSpec objects that were asked about.

        Raises:
            FileNotFoundError: If template_path does not exist.
            KeyboardInterrupt: If the user aborts the interview.
        """
        path = Path(template_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Template not found: {path}")

        self._template_path = str(path)
        self._template = path.read_text(encoding="utf-8")
        self._specs = parse_template_parameters(self._template)
        self._collected = []
        self._params = {}
        self._interview_complete = False

        if not self._specs:
            if not skip_missing_ok:
                self._print("No placeholders found in template. Nothing to collect.")
            self._interview_complete = True
            return []

        self._run_interview()
        return self._specs

    def ask_parameters(self, specs: list[ParameterSpec]) -> dict[str, Any]:
        """
        Run the Q&A session for an explicit list of parameter specs.

        Useful when you want to drive the interview without loading a file.

        Args:
            specs: Ordered list of ParameterSpec objects to ask about.

        Returns:
            Collected parameter mapping (name → coerced value).
        """
        self._specs = specs
        self._collected = []
        self._params = {}
        self._interview_complete = False
        self._run_interview()
        return dict(self._params)

    def get_parameters(self) -> dict[str, Any]:
        """
        Return the collected parameters as a plain dict.

        Returns:
            Mapping of parameter name → coerced Python value.  Empty if the
            interview has not completed.
        """
        return dict(self._params)

    def generate_mission(self) -> str:
        """
        Fill the loaded template with the collected parameters.

        Returns:
            The fully rendered mission document string.

        Raises:
            RuntimeError: If start() has not been called or the interview is
                          incomplete.
        """
        if self._template is None:
            raise RuntimeError(
                "deep_interview_not_started: call start() before generate_mission()."
            )
        if not self._interview_complete:
            raise RuntimeError(
                "deep_interview_incomplete: the interview has not finished yet."
            )
        return fill_template(self._template, self._params)

    def save_mission(self, output_path: str) -> str:
        """
        Write the filled mission document to *output_path*.

        Args:
            output_path: Destination file path.

        Returns:
            Absolute path of the written file.
        """
        content = self.generate_mission()
        out = Path(output_path).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
        self._print(f"Mission written to {out}")
        return str(out)

    def print_summary(self) -> None:
        """Print a summary table of the collected parameters."""
        if not self._params:
            self._print("[dim]No parameters collected.[/dim]")
            return

        if _RICH_AVAILABLE:
            console = self._get_console()
            table = Table(title="Collected Parameters", show_header=True, header_style="bold magenta")
            table.add_column("Parameter", style="cyan", no_wrap=True)
            table.add_column("Value")
            table.add_column("Type", style="dim")
            for cp in self._collected:
                spec = next((s for s in self._specs if s.name == cp.name), None)
                kind = spec.kind if spec else "string"
                table.add_row(cp.name, str(cp.value), kind)
            console.print(table)
        else:
            print("\n--- Collected Parameters ---")
            for cp in self._collected:
                print(f"  {cp.name}: {cp.value}")
            print()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_console(self) -> "Console":
        if self._console is None and _RICH_AVAILABLE:
            self._console = Console()
        return self._console  # type: ignore[return-value]

    def _print(self, message: str) -> None:
        if _RICH_AVAILABLE:
            self._get_console().print(message)
        else:
            # Strip basic markup for plain output.
            clean = re.sub(r"\[/?[^\]]*\]", "", message)
            print(clean)

    def _run_interview(self) -> None:
        """Drive the full interview session."""
        total = len(self._specs)

        if _RICH_AVAILABLE:
            console = self._get_console()
            console.print(Panel(
                f"[bold]Deep Interview[/bold]\n"
                f"[dim]Answer {total} question(s) to fill the mission template.[/dim]",
                style="blue",
            ))
        else:
            print(f"\n=== Deep Interview: {total} question(s) ===\n")

        for i, spec in enumerate(self._specs, start=1):
            if _RICH_AVAILABLE:
                cp = _ask_one_rich(self._get_console(), spec, i, total)
            else:
                cp = _ask_one_plain(spec, i, total)
            self._collected.append(cp)
            self._params[cp.name] = cp.value

        self._interview_complete = True

        if _RICH_AVAILABLE:
            self._get_console().print(
                Panel("[bold green]Interview complete![/bold green]", style="green")
            )
        else:
            print("\n=== Interview complete! ===\n")
