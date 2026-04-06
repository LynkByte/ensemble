"""Indexer tools: project_index, project_query, project_dependencies.

Lightweight file-level codebase index stored in SQLite, refreshed
incrementally using file modification times. Extracts exports, imports,
language, and file role per file.
"""

from __future__ import annotations

import contextlib
import fnmatch
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from ..config.defaults import INDEXER_IGNORED_DIRS, INDEXER_IGNORED_EXTENSIONS
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


def _extract_exports(content: str, language: str | None) -> list[dict]:
    """Extract exported symbols from file content."""
    if not language or not content:
        return []

    exports: list[dict] = []

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


def _extract_ts_js_exports(content: str, exports: list[dict]) -> None:
    """Extract exports from TypeScript/JavaScript."""
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
                }
            )


def _extract_python_exports(content: str, exports: list[dict]) -> None:
    """Extract exports from Python (top-level class/def, __all__)."""
    # Top-level classes
    for match in re.finditer(r"^class\s+(\w+)", content, re.MULTILINE):
        exports.append(
            {
                "name": match.group(1),
                "kind": "class",
                "line_number": content[: match.start()].count("\n") + 1,
            }
        )
    # Top-level functions
    for match in re.finditer(r"^def\s+(\w+)", content, re.MULTILINE):
        exports.append(
            {
                "name": match.group(1),
                "kind": "function",
                "line_number": content[: match.start()].count("\n") + 1,
            }
        )
    # __all__
    match = re.search(r"__all__\s*=\s*\[(.*?)\]", content, re.DOTALL)
    if match:
        for name_match in re.finditer(r"""["'](\w+)["']""", match.group(1)):
            # Don't duplicate if already found
            name = name_match.group(1)
            if not any(e["name"] == name for e in exports):
                exports.append({"name": name, "kind": "constant", "line_number": None})


def _extract_php_exports(content: str, exports: list[dict]) -> None:
    """Extract exports from PHP."""
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
                }
            )


def _extract_go_exports(content: str, exports: list[dict]) -> None:
    """Extract exports from Go (capitalized = exported)."""
    for match in re.finditer(r"^func\s+(\(?[A-Z]\w*)", content, re.MULTILINE):
        name = match.group(1).lstrip("(")
        exports.append(
            {
                "name": name,
                "kind": "function",
                "line_number": content[: match.start()].count("\n") + 1,
            }
        )
    for match in re.finditer(r"^type\s+([A-Z]\w+)\s+struct", content, re.MULTILINE):
        exports.append(
            {
                "name": match.group(1),
                "kind": "class",
                "line_number": content[: match.start()].count("\n") + 1,
            }
        )


def _extract_rust_exports(content: str, exports: list[dict]) -> None:
    """Extract exports from Rust (pub items)."""
    patterns = [
        (r"pub\s+fn\s+(\w+)", "function"),
        (r"pub\s+struct\s+(\w+)", "class"),
        (r"pub\s+enum\s+(\w+)", "type"),
        (r"pub\s+trait\s+(\w+)", "trait"),
    ]
    for pat, kind in patterns:
        for match in re.finditer(pat, content):
            exports.append(
                {
                    "name": match.group(1),
                    "kind": kind,
                    "line_number": content[: match.start()].count("\n") + 1,
                }
            )


def _extract_ruby_exports(content: str, exports: list[dict]) -> None:
    """Extract exports from Ruby."""
    for match in re.finditer(r"^\s*class\s+(\w+)", content, re.MULTILINE):
        exports.append(
            {
                "name": match.group(1),
                "kind": "class",
                "line_number": content[: match.start()].count("\n") + 1,
            }
        )
    for match in re.finditer(r"^\s*module\s+(\w+)", content, re.MULTILINE):
        exports.append(
            {
                "name": match.group(1),
                "kind": "module",
                "line_number": content[: match.start()].count("\n") + 1,
            }
        )
    for match in re.finditer(r"^\s*def\s+(\w+)", content, re.MULTILINE):
        exports.append(
            {
                "name": match.group(1),
                "kind": "function",
                "line_number": content[: match.start()].count("\n") + 1,
            }
        )


# ── Import extraction ─────────────────────────────────────────────


def _extract_imports(content: str, language: str | None) -> list[dict]:
    """Extract import statements from file content."""
    if not language or not content:
        return []

    imports: list[dict] = []

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
) -> dict:
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

    # Force: clear existing index
    if force:
        file_ids = [
            r[0]
            for r in conn.execute(
                "SELECT id FROM project_files WHERE project_path = ?",
                (project_str,),
            ).fetchall()
        ]
        if file_ids:
            placeholders = ",".join("?" * len(file_ids))
            conn.execute(
                f"DELETE FROM file_exports WHERE file_id IN ({placeholders})",  # noqa: S608
                file_ids,
            )
            conn.execute(
                f"DELETE FROM file_imports WHERE file_id IN ({placeholders})",  # noqa: S608
                file_ids,
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
        file_id = cursor.lastrowid

        # Extract and store exports
        exports = _extract_exports(content, language)
        for exp in exports:
            conn.execute(
                "INSERT OR IGNORE INTO file_exports (file_id, name, kind, line_number) "
                "VALUES (?, ?, ?, ?)",
                (file_id, exp["name"], exp["kind"], exp.get("line_number")),
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
) -> dict:
    """Query the project index — find files by type, path, or role.

    Returns compact file map for agent consumption.
    """
    project = str(Path(project_path).resolve())

    conditions = ["project_path = ?"]
    params: list = [project]

    if file_types:
        placeholders = ",".join("?" * len(file_types))
        conditions.append(f"language IN ({placeholders})")
        params.extend(file_types)

    if path_pattern:
        conditions.append("file_path LIKE ?")
        params.append(f"%{path_pattern}%")

    if query:
        # Search by role or file path containing query terms
        conditions.append("(file_path LIKE ? OR role LIKE ?)")
        params.extend([f"%{query}%", f"%{query}%"])

    where_clause = " AND ".join(conditions)
    rows = conn.execute(
        f"SELECT id, file_path, language, role, size_bytes, modified_at "  # noqa: S608
        f"FROM project_files WHERE {where_clause} "
        f"ORDER BY file_path",
        params,
    ).fetchall()

    files: list[dict] = []
    for r in rows:
        file_id = r[0]
        # Get exports
        export_rows = conn.execute(
            "SELECT name, kind FROM file_exports WHERE file_id = ?",
            (file_id,),
        ).fetchall()
        exports = [{"name": e[0], "kind": e[1]} for e in export_rows]

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
) -> dict:
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
