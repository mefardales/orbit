"""
Code Intelligence MCP Server.

Provides LSP-like diagnostics, symbol search, AST pattern matching,
and reference finding. Uses pragmatic CLI wrappers (e.g. grep, ast-grep)
rather than full LSP protocol.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .bootstrap import (
    McpServer,
    ToolDefinition,
    ToolResult,
    auto_start_stdio_mcp_server,
    error_result,
    text_result,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _exec(
    cmd: str,
    args: List[str],
    cwd: Optional[str] = None,
    timeout: int = 30,
) -> Tuple[str, str]:
    """Run a command and return (stdout, stderr). Tolerates non-zero exit codes
    when stdout is still available (e.g. tsc with type errors)."""
    try:
        result = subprocess.run(
            [cmd, *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        if e.stdout is not None:
            return e.stdout or "", e.stderr or ""
        raise
    except FileNotFoundError:
        raise FileNotFoundError(f"Command not found: {cmd}")


# ── Diagnostics ──────────────────────────────────────────────────────────────


@dataclass
class Diagnostic:
    file: str
    line: int
    character: int
    severity: str  # 'error' | 'warning'
    code: str
    message: str


_TSC_RE = re.compile(
    r"^(.+?)\((\d+),(\d+)\):\s+(error|warning)\s+(TS\d+):\s+(.+)$", re.MULTILINE
)


def parse_tsc_output(output: str, project_dir: str) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []
    for m in _TSC_RE.finditer(output):
        diagnostics.append(
            Diagnostic(
                file=str(Path(project_dir) / m.group(1)),
                line=int(m.group(2)),
                character=int(m.group(3)),
                severity=m.group(4),
                code=m.group(5),
                message=m.group(6),
            )
        )
    return diagnostics


def find_tsconfig(directory: str) -> Optional[str]:
    for candidate in ("tsconfig.json", "tsconfig.build.json"):
        p = Path(directory) / candidate
        if p.exists():
            return str(p)
    return None


def run_tsc_diagnostics(
    target: str,
    project_dir: str,
    severity: Optional[str] = None,
) -> Dict[str, Any]:
    tsconfig = find_tsconfig(project_dir)
    args = ["--noEmit", "--pretty", "false"]
    if tsconfig:
        args.extend(["--project", tsconfig])

    try:
        stdout, stderr = _exec("npx", ["tsc", *args], cwd=project_dir, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"diagnostics": [], "command": "npx tsc (not available)"}

    output = stdout + "\n" + stderr
    diagnostics = parse_tsc_output(output, project_dir)

    if target and not target.endswith("/") and Path(target).exists():
        basename = Path(target).name
        diagnostics = [
            d
            for d in diagnostics
            if d.file == target or d.file.endswith("/" + basename)
        ]

    return {
        "diagnostics": diagnostics,
        "command": f"npx tsc {' '.join(args)}",
    }


# ── Symbol extraction ────────────────────────────────────────────────────────


@dataclass
class DocumentSymbol:
    name: str
    kind: str
    line: int
    character: int
    end_line: Optional[int] = None


_SYMBOL_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    # TypeScript / JavaScript
    ("function", re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)")),
    ("class", re.compile(r"^(?:export\s+)?(?:abstract\s+)?class\s+(\w+)")),
    ("interface", re.compile(r"^(?:export\s+)?interface\s+(\w+)")),
    ("type", re.compile(r"^(?:export\s+)?type\s+(\w+)\s*=")),
    ("enum", re.compile(r"^(?:export\s+)?(?:const\s+)?enum\s+(\w+)")),
    ("variable", re.compile(r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*[=:]")),
    ("method", re.compile(r"^\s+(?:async\s+)?(\w+)\s*\([^)]*\)\s*(?::\s*\w+)?\s*\{")),
    ("property", re.compile(r"^\s+(?:readonly\s+)?(\w+)\s*[?:].*[;,]$")),
    # Python
    ("function", re.compile(r"^(?:async\s+)?def\s+(\w+)")),
    ("class", re.compile(r"^class\s+(\w+)")),
    # Go
    ("function", re.compile(r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)")),
    ("type", re.compile(r"^type\s+(\w+)\s+(?:struct|interface)")),
    # Rust
    ("function", re.compile(r"^(?:pub\s+)?(?:async\s+)?fn\s+(\w+)")),
    ("struct", re.compile(r"^(?:pub\s+)?struct\s+(\w+)")),
    ("enum", re.compile(r"^(?:pub\s+)?enum\s+(\w+)")),
    ("trait", re.compile(r"^(?:pub\s+)?trait\s+(\w+)")),
    ("impl", re.compile(r"^impl(?:<[^>]+>)?\s+(\w+)")),
]


def extract_symbols(content: str) -> List[DocumentSymbol]:
    symbols: List[DocumentSymbol] = []
    seen: Set[str] = set()
    lines = content.split("\n")

    for i, line in enumerate(lines):
        for kind, pattern in _SYMBOL_PATTERNS:
            m = pattern.match(line)
            if m and m.group(1):
                key = f"{kind}:{m.group(1)}:{i}"
                if key not in seen:
                    seen.add(key)
                    symbols.append(
                        DocumentSymbol(
                            name=m.group(1),
                            kind=kind,
                            line=i + 1,
                            character=line.index(m.group(1)),
                        )
                    )
    return symbols


# ── AST-grep ─────────────────────────────────────────────────────────────────


def find_sg_binary() -> Optional[str]:
    for binary in ("sg", "ast-grep"):
        if shutil.which(binary):
            return binary
    return None


def build_ast_grep_run_args(
    pattern: str,
    language: str,
    path: Optional[str] = None,
    max_results: Optional[int] = None,
    replacement: Optional[str] = None,
    dry_run: bool = True,
) -> List[str]:
    args = ["run", "--pattern", pattern, "--lang", language]
    if replacement:
        args.extend(["--rewrite", replacement])
        if not dry_run:
            args.append("--update-all")
    else:
        args.append("--json")
    if path:
        args.append(path)
    return args


def run_ast_grep(
    pattern: str,
    language: str,
    path: Optional[str] = None,
    max_results: Optional[int] = None,
    replacement: Optional[str] = None,
    dry_run: bool = True,
) -> Dict[str, Any]:
    sg = find_sg_binary()
    if not sg:
        return {"matches": [], "command": "ast-grep not installed. Install: npm i -g @ast-grep/cli"}

    args = build_ast_grep_run_args(pattern, language, path, max_results, replacement, dry_run)

    try:
        stdout, _ = _exec(sg, args, timeout=30)
        try:
            results = json.loads(stdout)
            matches = results if isinstance(results, list) else [results]
            if max_results:
                matches = matches[:max_results]
            return {"matches": matches, "command": f"{sg} {' '.join(args)}"}
        except json.JSONDecodeError:
            return {"matches": [{"output": stdout}], "command": f"{sg} {' '.join(args)}"}
    except Exception as e:
        return {"matches": [], "command": f"{sg} {' '.join(args)} (failed: {e})"}


# ── Workspace symbol search ──────────────────────────────────────────────────

CODE_EXTENSIONS: Set[str] = {
    ".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rs", ".java", ".c", ".cpp", ".h",
    ".cs", ".rb", ".swift", ".kt", ".scala", ".vue", ".svelte",
}

SKIP_DIRS: Set[str] = {"node_modules", "dist", "__pycache__", ".git", ".venv", "venv"}


def search_workspace_symbols(
    query: str,
    directory: str,
    max_results: int = 50,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    query_lower = query.lower()

    def walk(d: Path, depth: int) -> None:
        if depth > 6 or len(results) >= max_results:
            return
        try:
            entries = sorted(d.iterdir())
        except OSError:
            return
        for entry in entries:
            if len(results) >= max_results:
                return
            if entry.is_dir():
                if entry.name.startswith(".") or entry.name in SKIP_DIRS:
                    continue
                walk(entry, depth + 1)
            elif entry.is_file() and entry.suffix in CODE_EXTENSIONS:
                try:
                    content = entry.read_text("utf-8", errors="replace")
                    for sym in extract_symbols(content):
                        if query_lower in sym.name.lower():
                            results.append(
                                {
                                    "name": sym.name,
                                    "kind": sym.kind,
                                    "line": sym.line,
                                    "character": sym.character,
                                    "file": str(entry.relative_to(directory)),
                                }
                            )
                            if len(results) >= max_results:
                                return
                except OSError:
                    pass

    walk(Path(directory), 0)
    return results[:max_results]


# ── Find project root ────────────────────────────────────────────────────────


def _find_project_root(start: str, markers: Tuple[str, ...] = ("package.json", ".git", "pyproject.toml")) -> str:
    d = Path(start)
    if d.is_file():
        d = d.parent
    for _ in range(10):
        for marker in markers:
            if (d / marker).exists():
                return str(d)
        parent = d.parent
        if parent == d:
            break
        d = parent
    return str(Path(start).parent if Path(start).is_file() else Path(start))


# ── MCP Server implementation ────────────────────────────────────────────────


class CodeIntelServer:
    """MCP server providing code intelligence tools."""

    async def list_tools(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name="lsp_diagnostics",
                description="Get diagnostics (errors, warnings) for a file. Uses tsc --noEmit for TypeScript projects.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file": {"type": "string", "description": "Path to the source file"},
                        "severity": {"type": "string", "enum": ["error", "warning", "info", "hint"]},
                    },
                    "required": ["file"],
                },
            ),
            ToolDefinition(
                name="lsp_diagnostics_directory",
                description="Run project-level diagnostics on a directory using tsc --noEmit.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "directory": {"type": "string", "description": "Project directory to check"},
                        "strategy": {"type": "string", "enum": ["tsc", "auto"]},
                    },
                    "required": ["directory"],
                },
            ),
            ToolDefinition(
                name="lsp_document_symbols",
                description="Get a hierarchical outline of all symbols in a file.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file": {"type": "string", "description": "Path to the source file"},
                    },
                    "required": ["file"],
                },
            ),
            ToolDefinition(
                name="lsp_workspace_symbols",
                description="Search for symbols across the workspace by name.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Symbol name or pattern to search"},
                        "file": {"type": "string", "description": "Any file in the workspace (determines project root)"},
                    },
                    "required": ["query", "file"],
                },
            ),
            ToolDefinition(
                name="lsp_hover",
                description="Get type information at a specific position in a file (regex-based approximation).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file": {"type": "string"},
                        "line": {"type": "integer"},
                        "character": {"type": "integer"},
                    },
                    "required": ["file", "line", "character"],
                },
            ),
            ToolDefinition(
                name="lsp_find_references",
                description="Find all references to a symbol across the codebase using grep.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file": {"type": "string"},
                        "line": {"type": "integer"},
                        "character": {"type": "integer"},
                        "includeDeclaration": {"type": "boolean"},
                    },
                    "required": ["file", "line", "character"],
                },
            ),
            ToolDefinition(
                name="lsp_servers",
                description="List available diagnostic backends and their installation status.",
                input_schema={"type": "object", "properties": {}},
            ),
            ToolDefinition(
                name="ast_grep_search",
                description="Search for code patterns using AST matching with meta-variables ($VAR, $$$VARS).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "language": {"type": "string"},
                        "path": {"type": "string"},
                        "maxResults": {"type": "integer"},
                    },
                    "required": ["pattern", "language"],
                },
            ),
            ToolDefinition(
                name="ast_grep_replace",
                description="Replace code patterns using AST matching. dryRun=true (default) previews only.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "replacement": {"type": "string"},
                        "language": {"type": "string"},
                        "path": {"type": "string"},
                        "dryRun": {"type": "boolean"},
                    },
                    "required": ["pattern", "replacement", "language"],
                },
            ),
        ]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        a = arguments or {}

        if name == "lsp_diagnostics":
            file = a.get("file")
            if not file:
                return error_result("file is required")
            project_dir = _find_project_root(file, ("tsconfig.json", "package.json"))
            result = run_tsc_diagnostics(file, project_dir, a.get("severity"))
            diags = result["diagnostics"]
            return text_result({
                "file": file,
                "diagnosticCount": len(diags),
                "diagnostics": [vars(d) for d in diags],
                "command": result["command"],
            })

        elif name == "lsp_diagnostics_directory":
            directory = a.get("directory")
            if not directory:
                return error_result("directory is required")
            result = run_tsc_diagnostics("", directory)
            diags = result["diagnostics"]
            by_file: Dict[str, List[Dict[str, Any]]] = {}
            for d in diags:
                rel = str(Path(d.file).relative_to(directory)) if Path(d.file).is_relative_to(directory) else d.file
                by_file.setdefault(rel, []).append(vars(d))
            return text_result({
                "directory": directory,
                "totalErrors": sum(1 for d in diags if d.severity == "error"),
                "totalWarnings": sum(1 for d in diags if d.severity == "warning"),
                "fileCount": len(by_file),
                "diagnosticsByFile": by_file,
                "command": result["command"],
            })

        elif name == "lsp_document_symbols":
            file = a.get("file")
            if not file:
                return error_result("file is required")
            if not Path(file).exists():
                return error_result(f"File not found: {file}")
            content = Path(file).read_text("utf-8", errors="replace")
            symbols = extract_symbols(content)
            return text_result({
                "file": file,
                "symbolCount": len(symbols),
                "symbols": [vars(s) for s in symbols],
            })

        elif name == "lsp_workspace_symbols":
            query = a.get("query")
            file = a.get("file")
            if not query:
                return error_result("query is required")
            directory = _find_project_root(file or os.getcwd())
            symbols = search_workspace_symbols(query, directory)
            return text_result({"query": query, "resultCount": len(symbols), "symbols": symbols})

        elif name == "lsp_hover":
            file = a.get("file")
            line_num = a.get("line")
            char = a.get("character", 0)
            if not file or not line_num:
                return error_result("file and line are required")
            if not Path(file).exists():
                return error_result(f"File not found: {file}")
            content = Path(file).read_text("utf-8", errors="replace")
            lines = content.split("\n")
            target_line = lines[line_num - 1] if line_num <= len(lines) else ""
            # Extract word at position
            start, end = char, char
            while start > 0 and (start - 1 < len(target_line)) and target_line[start - 1].isalnum() or (start > 0 and start - 1 < len(target_line) and target_line[start - 1] == "_"):
                start -= 1
            while end < len(target_line) and (target_line[end].isalnum() or target_line[end] == "_"):
                end += 1
            word = target_line[start:end]
            symbols = extract_symbols(content)
            match = next((s for s in symbols if s.name == word), None)
            return text_result({
                "file": file,
                "position": {"line": line_num, "character": char},
                "word": word,
                "lineContent": target_line.strip(),
                "localDefinition": vars(match) if match else None,
                "note": "Regex-based approximation.",
            })

        elif name == "lsp_find_references":
            file = a.get("file")
            line_num = a.get("line")
            char = a.get("character", 0)
            include_decl = a.get("includeDeclaration", True)
            if not file or not line_num:
                return error_result("file and line are required")
            content = Path(file).read_text("utf-8", errors="replace")
            lines = content.split("\n")
            target_line = lines[line_num - 1] if line_num <= len(lines) else ""
            start, end = char, char
            while start > 0 and start - 1 < len(target_line) and (target_line[start - 1].isalnum() or target_line[start - 1] == "_"):
                start -= 1
            while end < len(target_line) and (target_line[end].isalnum() or target_line[end] == "_"):
                end += 1
            symbol = target_line[start:end]
            if not symbol:
                return error_result("Could not identify symbol at position")

            directory = _find_project_root(file)
            try:
                stdout, _ = _exec(
                    "grep",
                    ["-rn", "--include=*.ts", "--include=*.tsx", "--include=*.js",
                     "--include=*.jsx", "--include=*.py", "--include=*.go",
                     "--include=*.rs", "-w", symbol, directory],
                    timeout=15,
                )
                refs: List[Dict[str, Any]] = []
                for ref_line in stdout.strip().split("\n"):
                    if not ref_line:
                        continue
                    m = re.match(r"^(.+?):(\d+):(.+)$", ref_line)
                    if m:
                        refs.append({
                            "file": m.group(1),
                            "line": int(m.group(2)),
                            "content": m.group(3).strip(),
                        })

                if not include_decl:
                    decl_lines = {s.line for s in extract_symbols(content) if s.name == symbol}
                    norm_file = str(Path(file).resolve())
                    refs = [
                        r for r in refs
                        if str(Path(r["file"]).resolve()) != norm_file or r["line"] not in decl_lines
                    ]

                return text_result({
                    "symbol": symbol,
                    "includeDeclaration": include_decl,
                    "referenceCount": len(refs),
                    "references": refs[:100],
                })
            except Exception:
                return text_result({
                    "symbol": symbol,
                    "includeDeclaration": include_decl,
                    "referenceCount": 0,
                    "references": [],
                    "note": "grep search returned no results",
                })

        elif name == "lsp_servers":
            checks: Dict[str, Dict[str, Any]] = {}
            # Check tsc
            try:
                stdout, _ = _exec("npx", ["tsc", "--version"], timeout=10)
                checks["typescript"] = {"available": True, "version": stdout.strip()}
            except Exception:
                checks["typescript"] = {"available": False, "note": "Install: npm i -D typescript"}
            # Check ast-grep
            sg = find_sg_binary()
            checks["ast-grep"] = {"available": sg is not None, "version": sg} if sg else {"available": False, "note": "Install: npm i -g @ast-grep/cli"}
            # Check grep
            checks["grep"] = {"available": shutil.which("grep") is not None}
            return text_result({"servers": checks})

        elif name == "ast_grep_search":
            pattern = a.get("pattern")
            language = a.get("language")
            if not pattern or not language:
                return error_result("pattern and language are required")
            result = run_ast_grep(pattern, language, path=a.get("path"), max_results=a.get("maxResults"))
            return text_result(result)

        elif name == "ast_grep_replace":
            pattern = a.get("pattern")
            replacement = a.get("replacement")
            language = a.get("language")
            if not pattern or not replacement or not language:
                return error_result("pattern, replacement, and language are required")
            dry_run = a.get("dryRun", True)
            result = run_ast_grep(pattern, language, path=a.get("path"), replacement=replacement, dry_run=dry_run)
            result["dryRun"] = dry_run
            return text_result(result)

        return error_result(f"Unknown tool: {name}")

    async def close(self) -> None:
        pass


def main() -> None:
    auto_start_stdio_mcp_server("code_intel", CodeIntelServer())


if __name__ == "__main__":
    main()
