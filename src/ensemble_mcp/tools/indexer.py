"""Indexer tools: project_index, project_query, project_dependencies, project_snapshot.

Lightweight file-level codebase index stored in SQLite, refreshed
incrementally using file modification times. Extracts exports, imports,
language, and file role per file.

``project_snapshot`` generates a compact project baseline summary from
the indexed data, cached in SQLite with mtime-based invalidation.
"""

from __future__ import annotations

import contextlib
import fnmatch
import hashlib
import json
import re
import sqlite3
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..config.defaults import (
    INDEXER_IGNORED_DIRS,
    INDEXER_IGNORED_EXTENSIONS,
    SNAPSHOT_DEFAULT_EXPIRY_HOURS,
    SNAPSHOT_MAX_FILES_IN_SUMMARY,
)
from ..contracts.envelope import tool_handler
from ..contracts.errors import ErrorCode, ToolError
from ..state.idempotency import check_idempotency, store_idempotency

# ── Language detection ────────────────────────────────────────────

_EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".php": "php",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".java": "java",
    ".kt": "kotlin",
    ".swift": "swift",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".vue": "vue",
    ".svelte": "svelte",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xml": "xml",
    ".md": "markdown",
    ".sql": "sql",
    ".sh": "shell",
    ".bash": "shell",
    ".dockerfile": "dockerfile",
    ".tf": "terraform",
}

# ── Role detection heuristics ─────────────────────────────────────

_ROLE_PATTERNS: list[tuple[str, str]] = [
    # Tests
    (r"test[s_/]|spec[s_/]|__tests__", "test"),
    # Migrations
    (r"migrat", "migration"),
    # Configuration
    (r"config|\.env|settings|\.rc$", "config"),
    # Models / Entities
    (r"model[s]?/|entit|schema", "model"),
    # Controllers / Handlers
    (r"controller[s]?/|handler[s]?/|endpoint", "controller"),
    # Services / Use Cases
    (r"service[s]?/|usecase|use_case|interactor", "service"),
    # Middleware
    (r"middleware", "middleware"),
    # Routes
    (r"route[s]?/|router", "route"),
    # Views / Templates / Components
    (r"view[s]?/|template[s]?/|component[s]?/|pages?/", "view"),
    # Fixtures / Seeds
    (r"fixture|seed|factory", "fixture"),
    # Types / Interfaces
    (r"type[s]?\.(?:ts|py)|interface[s]?/", "type"),
    # Utilities / Helpers
    (r"util[s]?/|helper[s]?/|lib/", "utility"),
]

_ROLE_RE = [(re.compile(pat, re.IGNORECASE), role) for pat, role in _ROLE_PATTERNS]


def _detect_language(path: Path) -> str | None:
    """Detect language from file extension."""
    suffix = path.suffix.lower()
    if path.name.lower() == "dockerfile":
        return "dockerfile"
    return _EXTENSION_MAP.get(suffix)


def _detect_role(file_path: str) -> str | None:
    """Heuristic role detection from the file path."""
    for pattern, role in _ROLE_RE:
        if pattern.search(file_path):
            return role
    return None


# ── Export extraction (language-aware) ────────────────────────────


def _extract_exports(content: str, language: str | None) -> list[dict[str, Any]]:
    """Extract exported symbols from file content."""
    if not language or not content:
        return []

    exports: list[dict[str, Any]] = []

    if language in ("typescript", "javascript"):
        _extract_ts_js_exports(content, exports)
    elif language == "python":
        _extract_python_exports(content, exports)
    elif language == "php":
        _extract_php_exports(content, exports)
    elif language == "go":
        _extract_go_exports(content, exports)
    elif language == "rust":
        _extract_rust_exports(content, exports)
    elif language == "ruby":
        _extract_ruby_exports(content, exports)

    return exports


# ── Signature & docstring helpers ─────────────────────────────────


def _get_line_at_pos(content: str, pos: int) -> str:
    """Extract the full source line containing character offset *pos*.

    Strips trailing ``{``, ``:``, and whitespace. Caps at 300 chars.
    """
    line_start = content.rfind("\n", 0, pos) + 1
    line_end = content.find("\n", pos)
    if line_end == -1:
        line_end = len(content)
    line = content[line_start:line_end].strip().rstrip("{:").rstrip()
    return line[:300]


def _extract_python_docstring(lines: list[str], line_idx: int) -> str | None:
    """Scan lines below *line_idx* for a triple-quoted docstring.

    Handles both single-line (``\"\"\"text\"\"\"``) and multiline forms.
    Returns the docstring text stripped of quotes, capped at 500 chars,
    or ``None`` if no docstring is found.
    """
    # Look at the next non-blank line after the definition
    idx = line_idx + 1
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    if idx >= len(lines):
        return None

    stripped = lines[idx].strip()
    for quote in ('"""', "'''"):
        if stripped.startswith(quote):
            # Single-line docstring: """text"""
            rest = stripped[len(quote) :]
            close_idx = rest.find(quote)
            if close_idx >= 0 and close_idx + len(quote) == len(rest):
                text = rest[:close_idx].strip()
                return text[:500] if text else None
            # Multiline docstring
            doc_lines = [stripped[len(quote) :]]
            for j in range(idx + 1, min(idx + 50, len(lines))):
                if quote in lines[j]:
                    end_pos = lines[j].find(quote)
                    doc_lines.append(lines[j][:end_pos].strip())
                    break
                doc_lines.append(lines[j].strip())
            text = "\n".join(doc_lines).strip()
            return text[:500] if text else None
    return None


def _extract_block_doc_comment(content: str, match_start: int) -> str | None:
    """Extract a ``/** ... */`` block doc comment directly above *match_start*.

    Scans backwards from *match_start* for a closing ``*/``, then finds the
    opening ``/**``. Strips leading ``*`` prefixes on each line.
    Shared by TypeScript/JavaScript and PHP extractors.
    Returns the cleaned text capped at 500 chars, or ``None``.
    """
    # Walk backwards to find the */ that closes the comment
    before = content[:match_start].rstrip()
    if not before.endswith("*/"):
        return None
    # close_pos is the position of '*/' in the original content
    close_pos = len(before)
    open_pos = content.rfind("/**", 0, close_pos)
    if open_pos == -1:
        return None
    block = content[open_pos:close_pos].rstrip()
    # Strip /** prefix, */ suffix, and * line prefixes
    block = block.removeprefix("/**").removesuffix("*/").strip()
    cleaned_lines: list[str] = []
    for line in block.split("\n"):
        stripped = line.strip()
        if stripped.startswith("* "):
            stripped = stripped[2:]
        elif stripped == "*":
            stripped = ""
        cleaned_lines.append(stripped)
    text = "\n".join(cleaned_lines).strip()
    return text[:500] if text else None


def _extract_line_doc_comment(lines: list[str], line_idx: int, prefix: str) -> str | None:
    """Walk backwards from *line_idx* collecting consecutive doc-comment lines.

    Lines must start with *prefix* (e.g. ``//``, ``///``, ``#``).
    Shared by Go, Rust, and Ruby extractors.
    Returns the joined text capped at 500 chars, or ``None``.
    """
    collected: list[str] = []
    idx = line_idx - 1
    while idx >= 0:
        stripped = lines[idx].strip()
        if stripped.startswith(prefix):
            text = stripped[len(prefix) :].strip()
            collected.append(text)
            idx -= 1
        else:
            break
    if not collected:
        return None
    collected.reverse()
    text = "\n".join(collected).strip()
    return text[:500] if text else None


def _extract_ts_js_exports(content: str, exports: list[dict[str, Any]]) -> None:
    """Extract exports from TypeScript/JavaScript, including signatures and docstrings."""
    patterns = [
        (r"export\s+(?:default\s+)?class\s+(\w+)", "class"),
        (r"export\s+(?:default\s+)?function\s+(\w+)", "function"),
        (r"export\s+(?:const|let|var)\s+(\w+)", "constant"),
        (r"export\s+(?:type|interface)\s+(\w+)", "type"),
        (r"export\s+enum\s+(\w+)", "type"),
        (r"module\.exports\s*=\s*(?:class\s+)?(\w+)", "class"),
    ]
    for pat, kind in patterns:
        for match in re.finditer(pat, content):
            exports.append(
                {
                    "name": match.group(1),
                    "kind": kind,
                    "line_number": content[: match.start()].count("\n") + 1,
                    "signature": _get_line_at_pos(content, match.start()),
                    "docstring": _extract_block_doc_comment(content, match.start()),
                }
            )


def _extract_python_exports(content: str, exports: list[dict[str, Any]]) -> None:
    """Extract exports from Python (top-level class/def, __all__).

    Includes signatures and docstrings.
    """
    lines = content.split("\n")
    # Top-level classes
    for match in re.finditer(r"^class\s+(\w+)", content, re.MULTILINE):
        line_idx = content[: match.start()].count("\n")
        exports.append(
            {
                "name": match.group(1),
                "kind": "class",
                "line_number": line_idx + 1,
                "signature": _get_line_at_pos(content, match.start()),
                "docstring": _extract_python_docstring(lines, line_idx),
            }
        )
    # Top-level functions
    for match in re.finditer(r"^def\s+(\w+)", content, re.MULTILINE):
        line_idx = content[: match.start()].count("\n")
        exports.append(
            {
                "name": match.group(1),
                "kind": "function",
                "line_number": line_idx + 1,
                "signature": _get_line_at_pos(content, match.start()),
                "docstring": _extract_python_docstring(lines, line_idx),
            }
        )
    # __all__
    all_match = re.search(r"__all__\s*=\s*\[(.*?)\]", content, re.DOTALL)
    if all_match:
        for name_match in re.finditer(r"""["'](\w+)["']""", all_match.group(1)):
            # Don't duplicate if already found
            name = name_match.group(1)
            if not any(e["name"] == name for e in exports):
                exports.append(
                    {
                        "name": name,
                        "kind": "constant",
                        "line_number": None,
                        "signature": None,
                        "docstring": None,
                    }
                )


def _extract_php_exports(content: str, exports: list[dict[str, Any]]) -> None:
    """Extract exports from PHP, including signatures and docstrings."""
    patterns = [
        (r"(?:abstract\s+)?class\s+(\w+)", "class"),
        (r"interface\s+(\w+)", "interface"),
        (r"trait\s+(\w+)", "trait"),
        (r"function\s+(\w+)\s*\(", "function"),
    ]
    for pat, kind in patterns:
        for match in re.finditer(pat, content):
            exports.append(
                {
                    "name": match.group(1),
                    "kind": kind,
                    "line_number": content[: match.start()].count("\n") + 1,
                    "signature": _get_line_at_pos(content, match.start()),
                    "docstring": _extract_block_doc_comment(content, match.start()),
                }
            )


def _extract_go_exports(content: str, exports: list[dict[str, Any]]) -> None:
    """Extract exports from Go (capitalized = exported).

    Uses two function patterns: one for method receivers
    (``func (r *Receiver) Name()``) and one for standalone functions
    (``func Name()``). Also extracts struct and interface types.
    """
    lines = content.split("\n")
    # Methods with receiver: func (r *Receiver) Name(...)
    method_pat = r"^func\s+\(\w+\s+\*?\w+\)\s+([A-Z]\w+)"
    for match in re.finditer(method_pat, content, re.MULTILINE):
        line_idx = content[: match.start()].count("\n")
        exports.append(
            {
                "name": match.group(1),
                "kind": "function",
                "line_number": line_idx + 1,
                "signature": _get_line_at_pos(content, match.start()),
                "docstring": _extract_line_doc_comment(lines, line_idx, "//"),
            }
        )
    # Standalone exported functions: func Name(...)
    func_pat = r"^func\s+([A-Z]\w+)"
    for match in re.finditer(func_pat, content, re.MULTILINE):
        line_idx = content[: match.start()].count("\n")
        exports.append(
            {
                "name": match.group(1),
                "kind": "function",
                "line_number": line_idx + 1,
                "signature": _get_line_at_pos(content, match.start()),
                "docstring": _extract_line_doc_comment(lines, line_idx, "//"),
            }
        )
    # Exported structs and interfaces
    type_pat = r"^type\s+([A-Z]\w+)\s+(?:struct|interface)"
    for match in re.finditer(type_pat, content, re.MULTILINE):
        line_idx = content[: match.start()].count("\n")
        exports.append(
            {
                "name": match.group(1),
                "kind": "class",
                "line_number": line_idx + 1,
                "signature": _get_line_at_pos(content, match.start()),
                "docstring": _extract_line_doc_comment(lines, line_idx, "//"),
            }
        )


def _extract_rust_exports(content: str, exports: list[dict[str, Any]]) -> None:
    """Extract exports from Rust (pub items), including signatures and docstrings."""
    lines = content.split("\n")
    patterns = [
        (r"pub\s+fn\s+(\w+)", "function"),
        (r"pub\s+struct\s+(\w+)", "class"),
        (r"pub\s+enum\s+(\w+)", "type"),
        (r"pub\s+trait\s+(\w+)", "trait"),
    ]
    for pat, kind in patterns:
        for match in re.finditer(pat, content):
            line_idx = content[: match.start()].count("\n")
            exports.append(
                {
                    "name": match.group(1),
                    "kind": kind,
                    "line_number": line_idx + 1,
                    "signature": _get_line_at_pos(content, match.start()),
                    "docstring": _extract_line_doc_comment(lines, line_idx, "///"),
                }
            )


def _extract_ruby_exports(content: str, exports: list[dict[str, Any]]) -> None:
    """Extract exports from Ruby, including signatures and docstrings."""
    lines = content.split("\n")
    for match in re.finditer(r"^\s*class\s+(\w+)", content, re.MULTILINE):
        line_idx = content[: match.start()].count("\n")
        exports.append(
            {
                "name": match.group(1),
                "kind": "class",
                "line_number": line_idx + 1,
                "signature": _get_line_at_pos(content, match.start()),
                "docstring": _extract_line_doc_comment(lines, line_idx, "#"),
            }
        )
    for match in re.finditer(r"^\s*module\s+(\w+)", content, re.MULTILINE):
        line_idx = content[: match.start()].count("\n")
        exports.append(
            {
                "name": match.group(1),
                "kind": "module",
                "line_number": line_idx + 1,
                "signature": _get_line_at_pos(content, match.start()),
                "docstring": _extract_line_doc_comment(lines, line_idx, "#"),
            }
        )
    for match in re.finditer(r"^\s*def\s+(\w+)", content, re.MULTILINE):
        line_idx = content[: match.start()].count("\n")
        exports.append(
            {
                "name": match.group(1),
                "kind": "function",
                "line_number": line_idx + 1,
                "signature": _get_line_at_pos(content, match.start()),
                "docstring": _extract_line_doc_comment(lines, line_idx, "#"),
            }
        )


# ── Import extraction ─────────────────────────────────────────────


def _extract_imports(content: str, language: str | None) -> list[dict[str, str]]:
    """Extract import statements from file content."""
    if not language or not content:
        return []

    imports: list[dict[str, str]] = []

    if language in ("typescript", "javascript"):
        for match in re.finditer(
            r"""(?:import\s+.*?from\s+|require\s*\(\s*)["']([^"']+)["']""",
            content,
        ):
            imports.append({"import_path": match.group(1), "raw": match.group(0)})

    elif language == "python":
        pattern = r"^(?:from\s+(\S+)\s+import|import\s+(\S+))"
        for match in re.finditer(pattern, content, re.MULTILINE):
            path = match.group(1) or match.group(2)
            imports.append({"import_path": path, "raw": match.group(0)})

    elif language == "php":
        for match in re.finditer(r"(?:use|require_once|include)\s+([^\s;]+)", content):
            imports.append({"import_path": match.group(1), "raw": match.group(0)})

    elif language == "go":
        for match in re.finditer(r'"([^"]+)"', content):
            if "/" in match.group(1):
                imports.append({"import_path": match.group(1), "raw": match.group(0)})

    elif language == "rust":
        for match in re.finditer(r"use\s+([\w:]+)", content):
            imports.append({"import_path": match.group(1), "raw": match.group(0)})

    elif language == "ruby":
        for match in re.finditer(r"require(?:_relative)?\s+['\"]([^'\"]+)", content):
            imports.append({"import_path": match.group(1), "raw": match.group(0)})

    return imports


# ── Gitignore parsing ─────────────────────────────────────────────


def _load_gitignore_patterns(project_path: Path) -> list[str]:
    """Load .gitignore patterns from project root."""
    gitignore = project_path / ".gitignore"
    if not gitignore.is_file():
        return []
    try:
        lines = gitignore.read_text(encoding="utf-8").splitlines()
        return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
    except OSError:
        return []


def _is_ignored(
    rel_path: str,
    ignored_dirs: set[str],
    gitignore_patterns: list[str],
) -> bool:
    """Check if a relative path should be ignored."""
    parts = Path(rel_path).parts
    for part in parts:
        if part in ignored_dirs:
            return True
    for pattern in gitignore_patterns:
        if fnmatch.fnmatch(rel_path, pattern):
            return True
        if fnmatch.fnmatch(rel_path, f"**/{pattern}"):
            return True
    return False


# ── MCP Tool implementations ─────────────────────────────────────


@tool_handler(source="sqlite", confidence="exact")
async def project_index(
    conn: sqlite3.Connection,
    *,
    project_path: str,
    force: bool = False,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Build or refresh the codebase index for faster exploration.

    Scans the file tree, detects language, extracts exports/imports,
    and detects file roles. Uses mtime for incremental refresh.
    """
    cached = check_idempotency(conn, idempotency_key)
    if cached is not None:
        return cached

    project = Path(project_path).resolve()
    if not project.is_dir():
        raise ToolError(
            code=ErrorCode.NOT_FOUND_PROJECT,
            message=f"Project directory not found: {project_path}",
            details={"project_path": project_path},
        )

    project_str = str(project)
    gitignore_patterns = _load_gitignore_patterns(project)

    # Force: clear existing index using subqueries to avoid
    # SQLite's SQLITE_MAX_VARIABLE_NUMBER limit (default 999).
    if force:
        conn.execute(
            "DELETE FROM file_exports WHERE file_id IN "
            "(SELECT id FROM project_files WHERE project_path = ?)",
            (project_str,),
        )
        conn.execute(
            "DELETE FROM file_imports WHERE file_id IN "
            "(SELECT id FROM project_files WHERE project_path = ?)",
            (project_str,),
        )
        conn.execute(
            "DELETE FROM project_files WHERE project_path = ?",
            (project_str,),
        )

    # Load existing index for mtime comparison
    existing: dict[str, tuple[int, str]] = {}  # rel_path -> (file_id, modified_at)
    for row in conn.execute(
        "SELECT id, file_path, modified_at FROM project_files WHERE project_path = ?",
        (project_str,),
    ).fetchall():
        existing[row[1]] = (row[0], row[2])

    indexed_count = 0
    cached_count = 0

    # Walk the project tree
    for fp in project.rglob("*"):
        if not fp.is_file():
            continue

        rel = str(fp.relative_to(project))

        # Skip ignored paths
        if _is_ignored(rel, INDEXER_IGNORED_DIRS, gitignore_patterns):
            continue

        # Skip ignored extensions
        if fp.suffix.lower() in INDEXER_IGNORED_EXTENSIONS:
            continue

        stat = fp.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
        size = stat.st_size

        # Skip unchanged files (incremental)
        if rel in existing:
            file_id, old_mtime = existing[rel]
            if old_mtime == mtime and not force:
                cached_count += 1
                continue
            # File changed — delete old exports/imports and re-index
            conn.execute("DELETE FROM file_exports WHERE file_id = ?", (file_id,))
            conn.execute("DELETE FROM file_imports WHERE file_id = ?", (file_id,))
            conn.execute("DELETE FROM project_files WHERE id = ?", (file_id,))

        language = _detect_language(fp)
        role = _detect_role(rel)

        # Read file content for export/import extraction
        content = ""
        if language and size < 500_000:  # Skip files > 500KB
            with contextlib.suppress(OSError):
                content = fp.read_text(encoding="utf-8", errors="replace")

        # Insert file record
        cursor = conn.execute(
            "INSERT INTO project_files "
            "(project_path, file_path, language, role, size_bytes, modified_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (project_str, rel, language, role, size, mtime),
        )
        file_id = cursor.lastrowid or 0

        # Extract and store exports
        exports = _extract_exports(content, language)
        for exp in exports:
            conn.execute(
                "INSERT OR IGNORE INTO file_exports "
                "(file_id, name, kind, line_number, signature, docstring) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    file_id,
                    exp["name"],
                    exp["kind"],
                    exp.get("line_number"),
                    exp.get("signature"),
                    exp.get("docstring"),
                ),
            )

        # Extract and store imports
        imports = _extract_imports(content, language)
        for imp in imports:
            conn.execute(
                "INSERT INTO file_imports (file_id, import_path, raw_import) VALUES (?, ?, ?)",
                (file_id, imp["import_path"], imp["raw"]),
            )

        indexed_count += 1

    conn.commit()

    result = {
        "indexed": True,
        "files": indexed_count,
        "cached": cached_count,
        "total": indexed_count + cached_count,
    }
    store_idempotency(conn, idempotency_key, result)
    return result


@tool_handler(source="sqlite", confidence="exact")
async def project_query(
    conn: sqlite3.Connection,
    *,
    project_path: str,
    query: str | None = None,
    file_types: list[str] | None = None,
    path_pattern: str | None = None,
) -> dict[str, Any]:
    """Query the project index — find files by type, path, or role.

    Returns compact file map for agent consumption.
    """
    project = str(Path(project_path).resolve())

    conditions = ["project_path = ?"]
    params: list[Any] = [project]

    if file_types:
        placeholders = ",".join("?" * len(file_types))
        conditions.append(f"language IN ({placeholders})")
        params.extend(file_types)

    if path_pattern:
        conditions.append("file_path LIKE ?")
        params.append(f"%{path_pattern}%")

    if query:
        # Search by role, file path, or export name/signature/docstring
        conditions.append(
            "(file_path LIKE ? OR role LIKE ? OR id IN ("
            "SELECT file_id FROM file_exports "
            "WHERE name LIKE ? OR signature LIKE ? OR docstring LIKE ?"
            "))"
        )
        like_term = f"%{query}%"
        params.extend([like_term, like_term, like_term, like_term, like_term])

    where_clause = " AND ".join(conditions)
    rows = conn.execute(
        f"SELECT id, file_path, language, role, size_bytes, modified_at "  # noqa: S608
        f"FROM project_files WHERE {where_clause} "
        f"ORDER BY file_path",
        params,
    ).fetchall()

    files: list[dict[str, Any]] = []
    for r in rows:
        file_id = r[0]
        # Get exports
        export_rows = conn.execute(
            "SELECT name, kind, signature, docstring FROM file_exports WHERE file_id = ?",
            (file_id,),
        ).fetchall()
        exports = [
            {
                "name": e[0],
                "kind": e[1],
                "signature": e[2],
                "docstring": e[3],
            }
            for e in export_rows
        ]

        files.append(
            {
                "path": r[1],
                "language": r[2],
                "role": r[3],
                "size_bytes": r[4],
                "modified_at": r[5],
                "exports": exports,
            }
        )

    return {"files": files, "count": len(files)}


@tool_handler(source="sqlite", confidence="exact")
async def project_dependencies(
    conn: sqlite3.Connection,
    *,
    project_path: str,
    file_path: str,
) -> dict[str, Any]:
    """Get import/dependency graph for a specific file.

    Shows what a file imports and what imports it.
    """
    project = str(Path(project_path).resolve())

    # Find the file
    row = conn.execute(
        "SELECT id FROM project_files WHERE project_path = ? AND file_path = ?",
        (project, file_path),
    ).fetchone()

    if not row:
        raise ToolError(
            code=ErrorCode.NOT_FOUND_FILE,
            message=f"File not found in index: {file_path}",
            details={"project_path": project_path, "file_path": file_path},
        )

    file_id = row[0]

    # What this file imports
    import_rows = conn.execute(
        "SELECT import_path, raw_import FROM file_imports WHERE file_id = ?",
        (file_id,),
    ).fetchall()
    imports = [r[0] for r in import_rows]

    # What imports this file (reverse lookup)
    # Match by file stem or relative path
    file_stem = Path(file_path).stem
    imported_by_rows = conn.execute(
        "SELECT DISTINCT pf.file_path FROM file_imports fi "
        "JOIN project_files pf ON fi.file_id = pf.id "
        "WHERE pf.project_path = ? AND "
        "(fi.import_path LIKE ? OR fi.import_path LIKE ?)",
        (project, f"%{file_stem}%", f"%{file_path}%"),
    ).fetchall()
    imported_by = [r[0] for r in imported_by_rows if r[0] != file_path]

    # Related files (share common imports)
    related_rows = conn.execute(
        "SELECT DISTINCT pf.file_path FROM file_imports fi "
        "JOIN project_files pf ON fi.file_id = pf.id "
        "WHERE pf.project_path = ? AND pf.file_path != ? AND "
        "fi.import_path IN (SELECT import_path FROM file_imports WHERE file_id = ?)",
        (project, file_path, file_id),
    ).fetchall()
    related = [r[0] for r in related_rows][:10]  # Limit to top 10

    return {
        "file": file_path,
        "imports": imports,
        "imported_by": imported_by,
        "related": related,
    }


# ── Snapshot helpers ──────────────────────────────────────────────

# Framework detection: map indicator file → framework name
_FRAMEWORK_INDICATORS: list[tuple[str, str, str]] = [
    # (file pattern, language, framework)
    ("pyproject.toml", "python", ""),
    ("setup.py", "python", ""),
    ("manage.py", "python", "django"),
    ("artisan", "php", "laravel"),
    ("composer.json", "php", ""),
    ("package.json", "javascript", ""),
    ("next.config", "javascript", "next.js"),
    ("nuxt.config", "javascript", "nuxt"),
    ("angular.json", "typescript", "angular"),
    ("Cargo.toml", "rust", ""),
    ("go.mod", "go", ""),
    ("Gemfile", "ruby", ""),
    ("pom.xml", "java", "maven"),
    ("build.gradle", "java", "gradle"),
]

# Build tool detection: map file → build tool
_BUILD_TOOL_FILES: dict[str, str] = {
    "pyproject.toml": "pyproject.toml",
    "setup.py": "setup.py",
    "setup.cfg": "setup.cfg",
    "Makefile": "make",
    "package.json": "npm",
    "Cargo.toml": "cargo",
    "go.mod": "go modules",
    "Gemfile": "bundler",
    "composer.json": "composer",
    "pom.xml": "maven",
    "build.gradle": "gradle",
    "Dockerfile": "docker",
    "docker-compose.yml": "docker-compose",
    "docker-compose.yaml": "docker-compose",
}

# Test framework detection: map file/dir pattern → test framework
_TEST_FRAMEWORK_PATTERNS: list[tuple[str, str]] = [
    ("pytest.ini", "pytest"),
    ("conftest.py", "pytest"),
    ("jest.config", "jest"),
    ("vitest.config", "vitest"),
    ("phpunit.xml", "phpunit"),
    (".rspec", "rspec"),
]

# Directory role heuristics
_DIR_ROLE_MAP: list[tuple[str, str]] = [
    ("src", "source"),
    ("lib", "library"),
    ("app", "application"),
    ("tests", "tests"),
    ("test", "tests"),
    ("spec", "tests"),
    ("docs", "documentation"),
    ("config", "configuration"),
    ("scripts", "scripts"),
    ("migrations", "migrations"),
    ("public", "public assets"),
    ("static", "static assets"),
    ("templates", "templates"),
    ("views", "views"),
    ("components", "components"),
    ("pages", "pages"),
    ("api", "api"),
    ("models", "models"),
    ("services", "services"),
    ("utils", "utilities"),
    ("helpers", "helpers"),
]


def _compute_files_hash(conn: sqlite3.Connection, project_path: str) -> str:
    """Compute a hash of all indexed file mtimes for cache invalidation."""
    rows = conn.execute(
        "SELECT file_path, modified_at FROM project_files "
        "WHERE project_path = ? ORDER BY file_path",
        (project_path,),
    ).fetchall()
    hasher = hashlib.sha256()
    for row in rows:
        hasher.update(f"{row[0]}:{row[1]}\n".encode())
    return hasher.hexdigest()[:16]


def _generate_snapshot(conn: sqlite3.Connection, project_path: str) -> dict[str, Any]:
    """Generate a compact project baseline summary from indexed data.

    Queries the ``project_files``, ``file_exports``, and ``file_imports``
    tables to build a summary of the project's language, framework,
    conventions, directory structure, test setup, build tools, and key files.

    Returns:
        Dict with project metadata suitable for embedding in agent prompts.
    """
    # ── Gather indexed files ──────────────────────────────────────
    rows = conn.execute(
        "SELECT id, file_path, language, role, size_bytes FROM project_files "
        "WHERE project_path = ? ORDER BY file_path",
        (project_path,),
    ).fetchall()

    if not rows:
        return {
            "project_path": project_path,
            "language": "unknown",
            "framework": None,
            "conventions": [],
            "structure": {},
            "test_setup": {"framework": "unknown", "pattern_dir": ""},
            "build_tools": [],
            "key_files": [],
        }

    # ── Language detection ─────────────────────────────────────────
    lang_counts: Counter[str] = Counter()
    for row in rows:
        if row[2]:  # language column
            lang_counts[row[2]] += 1

    primary_language = lang_counts.most_common(1)[0][0] if lang_counts else "unknown"

    # ── Framework detection ───────────────────────────────────────
    file_paths = {row[1] for row in rows}
    file_basenames = {Path(fp).name for fp in file_paths}
    # Top-level files only (files with no parent directory in the relative path)
    top_level_basenames = {Path(fp).name for fp in file_paths if len(Path(fp).parts) == 1}
    detected_framework: str | None = None

    # Indicator files that must be at the project root to count
    _ROOT_ONLY_INDICATORS: set[str] = {"manage.py", "artisan"}

    for indicator_file, _lang, framework in _FRAMEWORK_INDICATORS:
        # For root-only indicators, only match top-level files
        if indicator_file in _ROOT_ONLY_INDICATORS:
            names_to_check = top_level_basenames
        else:
            names_to_check = file_basenames
        if any(bn.startswith(indicator_file) for bn in names_to_check) and framework:
            detected_framework = framework
            break

    # ── Build tools ───────────────────────────────────────────────
    build_tools: list[str] = []
    for build_file, tool_name in _BUILD_TOOL_FILES.items():
        if build_file in file_basenames and tool_name not in build_tools:
            build_tools.append(tool_name)

    # ── Directory structure ───────────────────────────────────────
    structure: dict[str, str] = {}
    top_dirs: set[str] = set()
    for row in rows:
        parts = Path(row[1]).parts
        if len(parts) > 1:
            top_dirs.add(parts[0])

    for dirname in sorted(top_dirs):
        for pattern, role in _DIR_ROLE_MAP:
            if dirname.lower() == pattern:
                structure[dirname] = role
                break
        else:
            # Default: use dirname as-is (no role detected)
            if dirname not in structure:
                structure[dirname] = ""

    # Remove dirs with no detected role to keep compact
    structure = {k: v for k, v in structure.items() if v}

    # ── Test setup ────────────────────────────────────────────────
    test_framework = "unknown"
    test_dir = ""

    for pattern, fw in _TEST_FRAMEWORK_PATTERNS:
        if any(pattern in fp for fp in file_paths):
            test_framework = fw
            break

    # Find the test directory (explicit preference order for determinism)
    for candidate in ["tests", "test", "spec", "__tests__"]:
        matching = [d for d in top_dirs if d.lower() == candidate]
        if matching:
            test_dir = matching[0]
            break

    # ── Conventions ───────────────────────────────────────────────
    conventions: list[str] = []

    # Naming conventions
    snake_count = sum(1 for fp in file_paths if "_" in Path(fp).stem)
    camel_count = sum(1 for fp in file_paths if re.search(r"[a-z][A-Z]", Path(fp).stem))
    if snake_count > camel_count and snake_count > 3:
        conventions.append("snake_case file naming")
    elif camel_count > snake_count and camel_count > 3:
        conventions.append("camelCase file naming")

    # Check for common patterns
    role_counts: Counter[str] = Counter()
    for row in rows:
        if row[3]:  # role column
            role_counts[row[3]] += 1

    if role_counts.get("test", 0) > 0:
        conventions.append(f"test files present ({role_counts['test']} files)")
    if role_counts.get("config", 0) > 0:
        conventions.append("configuration files present")
    if any(fp.endswith("__init__.py") for fp in file_paths):
        conventions.append("Python package structure (__init__.py)")

    # ── Key files ─────────────────────────────────────────────────
    key_files: list[dict[str, Any]] = []

    # Get files with exports (most likely important)
    export_file_ids = conn.execute(
        "SELECT DISTINCT file_id FROM file_exports WHERE file_id IN "
        "(SELECT id FROM project_files WHERE project_path = ?)",
        (project_path,),
    ).fetchall()
    export_file_id_set = {r[0] for r in export_file_ids}

    # Batch-fetch exports for all relevant files in a single query to avoid N+1
    if export_file_id_set:
        placeholders = ",".join("?" for _ in export_file_id_set)
        all_export_rows = conn.execute(
            f"SELECT file_id, name FROM file_exports WHERE file_id IN ({placeholders})",  # noqa: S608
            list(export_file_id_set),
        ).fetchall()

        # Group exports by file_id, keeping at most 10 per file
        exports_by_file: dict[int, list[str]] = {}
        for file_id_val, export_name in all_export_rows:
            file_exports = exports_by_file.setdefault(file_id_val, [])
            if len(file_exports) < 10:
                file_exports.append(export_name)
    else:
        exports_by_file = {}

    for row in rows:
        file_id, fp, lang, role, size_bytes = row
        if file_id not in export_file_id_set:
            continue

        key_files.append(
            {
                "path": fp,
                "role": role or "",
                "exports": exports_by_file.get(file_id, []),
            }
        )

        if len(key_files) >= SNAPSHOT_MAX_FILES_IN_SUMMARY:
            break

    return {
        "project_path": project_path,
        "language": primary_language,
        "framework": detected_framework,
        "conventions": conventions,
        "structure": structure,
        "test_setup": {"framework": test_framework, "pattern_dir": test_dir},
        "build_tools": build_tools,
        "key_files": key_files,
    }


@tool_handler(source="sqlite", confidence="exact")
async def project_snapshot(
    conn: sqlite3.Connection,
    *,
    project_path: str,
    force: bool = False,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Generate or return a cached compact project baseline summary.

    Queries the codebase index to build a summary of the project's
    language, framework, conventions, directory structure, test setup,
    build tools, and key files. Results are cached in the
    ``project_snapshots`` table with mtime-based invalidation.

    Args:
        conn: SQLite connection.
        project_path: Absolute or relative path to the project root.
        force: If True, regenerate even if a valid cache entry exists.
        idempotency_key: Optional idempotency key for cache writes.

    Returns:
        Dict with ``snapshot``, ``cached`` flag, and ``files_hash``.
    """
    cached_result = check_idempotency(conn, idempotency_key)
    if cached_result is not None:
        return cached_result

    project = str(Path(project_path).resolve())

    # Check if project has been indexed
    file_count = conn.execute(
        "SELECT COUNT(*) FROM project_files WHERE project_path = ?",
        (project,),
    ).fetchone()[0]

    if file_count == 0:
        raise ToolError(
            code=ErrorCode.NOT_FOUND_PROJECT,
            message=f"Project not indexed: {project_path}. Run project_index first.",
            details={"project_path": project_path},
        )

    # Compute current files hash
    current_hash = _compute_files_hash(conn, project)

    # Check cache (unless force refresh)
    if not force:
        cache_row = conn.execute(
            "SELECT snapshot_json, files_hash, expires_at FROM project_snapshots "
            "WHERE project_path = ? AND expires_at > datetime('now')",
            (project,),
        ).fetchone()

        if cache_row and cache_row[1] == current_hash:
            snapshot = json.loads(cache_row[0])
            result: dict[str, Any] = {
                "snapshot": snapshot,
                "cached": True,
                "files_hash": current_hash,
            }
            store_idempotency(conn, idempotency_key, result)
            return result

    # Generate fresh snapshot
    snapshot = _generate_snapshot(conn, project)

    # Store in cache
    assert isinstance(SNAPSHOT_DEFAULT_EXPIRY_HOURS, int) and SNAPSHOT_DEFAULT_EXPIRY_HOURS > 0
    expiry_clause = f"+{SNAPSHOT_DEFAULT_EXPIRY_HOURS} hours"
    conn.execute(
        "INSERT OR REPLACE INTO project_snapshots "
        "(project_path, snapshot_json, files_hash, created_at, expires_at) "
        "VALUES (?, ?, ?, datetime('now'), datetime('now', ?))",
        (project, json.dumps(snapshot), current_hash, expiry_clause),
    )
    conn.commit()

    result = {
        "snapshot": snapshot,
        "cached": False,
        "files_hash": current_hash,
    }
    store_idempotency(conn, idempotency_key, result)
    return result
