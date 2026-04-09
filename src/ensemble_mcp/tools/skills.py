"""Skills tools: skills_discover, skills_suggest, skills_generate.

Discovery scans tool-native skill locations (.ai/skills/, .claude/skills/, etc.),
embeds content, and returns relevant skills via semantic search. Skill file content
and pre-computed embeddings are cached in SQLite using mtime-based invalidation
(same pattern as ``project_index``).

Suggestion clusters similar patterns by embedding similarity (>= 0.75 threshold)
and proposes reusable skills from groups with >= min_cluster_size patterns.

Generation accepts/dismisses/defers suggestions and writes Markdown skill files.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from ..config.defaults import (
    CLUSTER_SIMILARITY_THRESHOLD,
    DEFAULT_MIN_CLUSTER_SIZE,
    DEFAULT_SKILL_OUTPUT_DIR,
    DEFAULT_STALE_THRESHOLD_DAYS,
    SKILL_SCAN_DIRECTORIES,
)
from ..contracts.envelope import tool_handler
from ..contracts.errors import ErrorCode, ToolError
from ..memory.embeddings import EmbeddingModel
from ..memory.similarity import cosine_similarity
from ..state.idempotency import check_idempotency, store_idempotency

# ── Internal helpers ──────────────────────────────────────────────


def _scan_skill_files(
    project_path: str,
    conn: sqlite3.Connection,
    model: EmbeddingModel,
) -> list[dict[str, Any]]:
    """Walk known skill directories, cache content and embeddings in SQLite.

    Uses mtime-based incremental caching (same pattern as ``project_index``):
    filesystem walk is always performed (cheap), but file reads and embedding
    computation are skipped for unchanged files. Deleted files are pruned
    from the cache.

    Returns cached entries with keys: ``name``, ``path``, ``source_tool``,
    ``content``, ``embedding`` (raw bytes).
    """
    project = Path(project_path).resolve()
    if not project.is_dir():
        raise ToolError(
            code=ErrorCode.NOT_FOUND_PROJECT,
            message=f"Project directory not found: {project_path}",
            details={"project_path": project_path},
        )

    project_str = str(project)

    # Load existing cache: {file_path: (id, modified_at)}
    existing: dict[str, tuple[int, str]] = {}
    for row in conn.execute(
        "SELECT id, file_path, modified_at FROM skill_file_cache WHERE project_path = ?",
        (project_str,),
    ).fetchall():
        existing[row[1]] = (row[0], row[2])

    for skill_dir in SKILL_SCAN_DIRECTORIES:
        full_dir = project / skill_dir
        if not full_dir.is_dir():
            continue
        for fp in full_dir.rglob("*"):
            if fp.is_file() and fp.suffix in (".md", ".txt", ".yaml", ".yml"):
                rel = str(fp.relative_to(project))

                # Get mtime as ISO string (same serialisation as project_index)
                try:
                    stat = fp.stat()
                except OSError:
                    continue
                mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
                size = stat.st_size

                # Skip unchanged files
                if rel in existing:
                    _, old_mtime = existing[rel]
                    if old_mtime == mtime:
                        continue

                # Skip files > 500KB to avoid excessive memory use
                if size > 500_000:
                    continue

                # File is new or changed — read content and compute embedding
                try:
                    content = fp.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue

                # Determine source tool
                source_tool = "unknown"
                if ".ai/skills" in rel:
                    source_tool = "opencode"
                elif ".claude/skills" in rel:
                    source_tool = "claude-code"
                elif ".cursor/rules" in rel:
                    source_tool = "cursor"
                elif ".github/copilot" in rel:
                    source_tool = "copilot"

                embedding = model.embed(content[:500])
                emb_blob = embedding.tobytes()

                conn.execute(
                    "INSERT OR REPLACE INTO skill_file_cache "
                    "(project_path, file_path, name, source_tool, content, embedding, modified_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (project_str, rel, fp.stem, source_tool, content, emb_blob, mtime),
                )

    # Remove cache entries for files that no longer exist on disk
    for cached_path in existing:
        full_fp = project / cached_path
        if not full_fp.exists():
            conn.execute(
                "DELETE FROM skill_file_cache WHERE project_path = ? AND file_path = ?",
                (project_str, cached_path),
            )

    conn.commit()

    # Return all cached entries for this project
    rows = conn.execute(
        "SELECT name, file_path, source_tool, content, embedding "
        "FROM skill_file_cache WHERE project_path = ?",
        (project_str,),
    ).fetchall()

    return [
        {
            "name": r[0],
            "path": r[1],
            "source_tool": r[2],
            "content": r[3],
            "embedding": r[4],
        }
        for r in rows
    ]


def _track_skill_usage(
    conn: sqlite3.Connection,
    skill_path: str,
    project: str,
) -> None:
    """Update skill_usage_tracking for a matched skill."""
    conn.execute(
        "INSERT INTO skill_usage_tracking (skill_path, project, last_matched_at, match_count) "
        "VALUES (?, ?, datetime('now'), 1) "
        "ON CONFLICT(skill_path, project) DO UPDATE SET "
        "last_matched_at = datetime('now'), match_count = match_count + 1",
        (skill_path, project),
    )
    conn.commit()


def _cluster_patterns(
    patterns: list[dict[str, Any]],
    threshold: float = CLUSTER_SIMILARITY_THRESHOLD,
) -> list[list[int]]:
    """Single-linkage agglomerative clustering by embedding cosine similarity.

    Returns list of clusters, each cluster a list of pattern IDs.
    """
    if not patterns:
        return []

    # Pre-parse embeddings
    emb_map: dict[int, np.ndarray] = {}
    for p in patterns:
        emb_map[p["id"]] = np.frombuffer(p["embedding"], dtype=np.float32)

    clusters: list[list[int]] = []

    for pattern in patterns:
        pid = pattern["id"]
        emb = emb_map[pid]
        best_cluster: int | None = None
        best_score = 0.0

        for i, cluster in enumerate(clusters):
            for member_id in cluster:
                score = cosine_similarity(emb, emb_map[member_id])
                if score >= threshold and score > best_score:
                    best_cluster = i
                    best_score = score

        if best_cluster is not None:
            clusters[best_cluster].append(pid)
        else:
            clusters.append([pid])

    return clusters


def _derive_name(patterns: list[dict[str, Any]]) -> str:
    """Derive a slug name from the most common words in pattern names."""
    words: dict[str, int] = {}
    for p in patterns:
        for word in p["name"].lower().replace("-", " ").split():
            if len(word) > 2:  # skip tiny words
                words[word] = words.get(word, 0) + 1
    top_words = sorted(words, key=lambda w: words[w], reverse=True)[:3]
    return "-".join(top_words) if top_words else "unnamed-skill"


def _generate_skill_content(patterns: list[dict[str, Any]], proposed_name: str) -> str:
    """Generate Markdown skill content from clustered patterns (zero-LLM)."""
    contexts: set[str] = set()
    approaches: set[str] = set()
    outcomes: list[str] = []

    for p in patterns:
        contexts.add(p["context"])
        approaches.add(p["approach"])
        outcomes.append(f"- **{p['name']}:** {p['outcome']}")

    return f"""# {proposed_name}

> Auto-generated by Ensemble Skill Intelligence from {len(patterns)} similar patterns.

## When to Apply

{chr(10).join(f"- {c}" for c in contexts)}

## Approach

{chr(10).join(f"- {a}" for a in approaches)}

## Learned Outcomes

{chr(10).join(outcomes)}

---
*Source patterns: {", ".join(str(p["id"]) for p in patterns)}*
*Generated: {datetime.now().strftime("%Y-%m-%d")}*
"""


# ── MCP Tool implementations ─────────────────────────────────────


@tool_handler(source="local", confidence="exact")
async def skills_discover(
    model: EmbeddingModel,
    conn: sqlite3.Connection,
    *,
    project_path: str,
    query: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Discover skill files across known AI-tool skill directories.

    Optionally filters by semantic ``query`` against skill content.
    Updates usage tracking for returned skills.
    """
    cached = check_idempotency(conn, idempotency_key)
    if cached is not None:
        return cached

    skill_files = _scan_skill_files(project_path, conn, model)

    detected: list[dict[str, Any]] = []
    snippets: list[dict[str, Any]] = []

    if query and skill_files:
        # Semantic search mode — use pre-computed embeddings from cache
        query_emb = model.embed(query)
        scored: list[tuple[dict[str, Any], float]] = []
        for sf in skill_files:
            content_emb = np.frombuffer(sf["embedding"], dtype=np.float32)
            score = cosine_similarity(query_emb, content_emb)
            scored.append((sf, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        for sf, score in scored[:5]:
            if score >= 0.3:
                detected.append(
                    {
                        "name": sf["name"],
                        "source_tool": sf["source_tool"],
                        "path": sf["path"],
                        "confidence": round(score, 3),
                    }
                )
                snippets.append(
                    {
                        "content": sf["content"][:500],
                        "relevance": round(score, 3),
                    }
                )
    else:
        # Return all discovered skills
        for sf in skill_files:
            detected.append(
                {
                    "name": sf["name"],
                    "source_tool": sf["source_tool"],
                    "path": sf["path"],
                    "confidence": 1.0,
                }
            )

    # Track usage for returned skills
    for skill in detected:
        _track_skill_usage(conn, skill["path"], project_path)

    result: dict[str, Any] = {"detected": detected}
    if snippets:
        result["snippets"] = snippets

    store_idempotency(conn, idempotency_key, result)
    return result


@tool_handler(source="sqlite", confidence="exact")
async def skills_suggest(
    model: EmbeddingModel,  # noqa: ARG001  — reserved for future clustering improvements
    conn: sqlite3.Connection,
    *,
    project_path: str,
    min_cluster_size: int = DEFAULT_MIN_CLUSTER_SIZE,
    stale_threshold_days: int = DEFAULT_STALE_THRESHOLD_DAYS,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Detect recurring patterns and suggest them as reusable skills.

    Clusters patterns by embedding similarity (>= 0.75). Clusters with
    >= ``min_cluster_size`` members become skill suggestions.
    Also detects stale skills that haven't been matched recently.
    """
    cached = check_idempotency(conn, idempotency_key)
    if cached is not None:
        return cached

    # Load all patterns for project
    rows = conn.execute(
        "SELECT id, name, context, approach, outcome, embedding "
        "FROM patterns WHERE project = ? OR project IS NULL",
        (project_path,),
    ).fetchall()

    patterns = [
        {
            "id": r[0],
            "name": r[1],
            "context": r[2],
            "approach": r[3],
            "outcome": r[4],
            "embedding": r[5],
        }
        for r in rows
    ]

    # Cluster by embedding similarity
    clusters = _cluster_patterns(patterns, CLUSTER_SIMILARITY_THRESHOLD)

    # Filter viable clusters
    viable = [c for c in clusters if len(c) >= min_cluster_size]

    # Exclude already-resolved suggestions
    existing_pids: set[int] = set()
    for row in conn.execute(
        "SELECT pattern_id FROM skill_suggestion_patterns sp "
        "JOIN skill_suggestions s ON sp.suggestion_id = s.id "
        "WHERE s.project = ? AND s.status IN ('accepted', 'dismissed')",
        (project_path,),
    ).fetchall():
        existing_pids.add(row[0])

    suggestions: list[dict[str, Any]] = []
    for cluster_ids in viable:
        if all(pid in existing_pids for pid in cluster_ids):
            continue

        cluster_patterns = [p for p in patterns if p["id"] in cluster_ids]
        proposed_name = _derive_name(cluster_patterns)
        proposed_content = _generate_skill_content(cluster_patterns, proposed_name)

        # Calculate cluster confidence (average pairwise similarity)
        embs = [np.frombuffer(p["embedding"], dtype=np.float32) for p in cluster_patterns]
        sims: list[float] = []
        for i, e1 in enumerate(embs):
            for e2 in embs[i + 1 :]:
                sims.append(cosine_similarity(e1, e2))
        confidence = float(np.mean(sims)) if sims else 0.0

        # Persist suggestion
        cursor = conn.execute(
            "INSERT INTO skill_suggestions "
            "(project, proposed_name, proposed_content, theme, confidence) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                project_path,
                proposed_name,
                proposed_content,
                f"Cluster of {len(cluster_ids)} similar patterns",
                confidence,
            ),
        )
        suggestion_id = cursor.lastrowid
        for pid in cluster_ids:
            conn.execute(
                "INSERT INTO skill_suggestion_patterns (suggestion_id, pattern_id) VALUES (?, ?)",
                (suggestion_id, pid),
            )

        suggestions.append(
            {
                "id": suggestion_id,
                "pattern_ids": cluster_ids,
                "theme": f"Cluster of {len(cluster_ids)} similar patterns",
                "confidence": round(confidence, 3),
                "proposed_name": proposed_name,
                "proposed_content": proposed_content,
            }
        )

    conn.commit()

    # Detect stale skills
    stale_cutoff = (datetime.now() - timedelta(days=stale_threshold_days)).isoformat()
    stale_rows = conn.execute(
        "SELECT skill_path, last_matched_at, match_count "
        "FROM skill_usage_tracking "
        "WHERE project = ? AND (last_matched_at IS NULL OR last_matched_at < ?)",
        (project_path, stale_cutoff),
    ).fetchall()

    stale_skills: list[dict[str, Any]] = []
    for r in stale_rows:
        last_matched = r[1]
        if last_matched:
            days_unused = (datetime.now() - datetime.fromisoformat(last_matched)).days
        else:
            days_unused = stale_threshold_days
        stale_skills.append(
            {
                "path": r[0],
                "last_matched_at": last_matched,
                "days_unused": days_unused,
            }
        )

    result = {"suggestions": suggestions, "stale_skills": stale_skills}
    store_idempotency(conn, idempotency_key, result)
    return result


@tool_handler(source="sqlite", confidence="exact")
async def skills_generate(
    conn: sqlite3.Connection,
    *,
    suggestion_id: int,
    action: str = "accept",
    output_dir: str = DEFAULT_SKILL_OUTPUT_DIR,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Accept, dismiss, or defer a skill suggestion.

    On accept: writes a Markdown skill file to ``output_dir``.
    On dismiss: suppresses the suggestion permanently.
    On defer: leaves the suggestion pending for future review.
    """
    cached = check_idempotency(conn, idempotency_key)
    if cached is not None:
        return cached

    row = conn.execute(
        "SELECT id, proposed_name, proposed_content, status, project "
        "FROM skill_suggestions WHERE id = ?",
        (suggestion_id,),
    ).fetchone()

    if not row:
        raise ToolError(
            code=ErrorCode.NOT_FOUND_SKILL_SUGGESTION,
            message=f"No skill suggestion with id {suggestion_id}",
            details={"suggestion_id": suggestion_id},
        )

    current_status = row[3]
    if current_status in ("accepted", "dismissed"):
        raise ToolError(
            code=ErrorCode.CONFLICT_ALREADY_RESOLVED,
            message=f"Suggestion {suggestion_id} is already {current_status}",
            details={"suggestion_id": suggestion_id, "status": current_status},
        )

    if action not in ("accept", "dismiss", "defer"):
        raise ToolError(
            code=ErrorCode.VALIDATION_INVALID_VALUE,
            message=f"Invalid action '{action}'. Must be accept, dismiss, or defer",
            details={"action": action},
        )

    if action == "dismiss":
        conn.execute(
            "UPDATE skill_suggestions SET status = 'dismissed', "
            "resolved_at = datetime('now') WHERE id = ?",
            (suggestion_id,),
        )
        conn.commit()
        result = {"generated": False, "status": "dismissed"}
        store_idempotency(conn, idempotency_key, result)
        return result

    if action == "defer":
        conn.execute(
            "UPDATE skill_suggestions SET status = 'deferred' WHERE id = ?",
            (suggestion_id,),
        )
        conn.commit()
        result = {"generated": False, "status": "deferred"}
        store_idempotency(conn, idempotency_key, result)
        return result

    # action == "accept"
    proposed_name = row[1]
    proposed_content = row[2]
    project = row[4]

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    file_name = f"{proposed_name}.md"
    file_path = output_path / file_name
    file_path.write_text(proposed_content, encoding="utf-8")

    conn.execute(
        "UPDATE skill_suggestions SET status = 'accepted', "
        "resolved_at = datetime('now'), generated_path = ? WHERE id = ?",
        (str(file_path), suggestion_id),
    )
    conn.execute(
        "INSERT OR IGNORE INTO skill_usage_tracking (skill_path, project) VALUES (?, ?)",
        (str(file_path), project),
    )
    conn.commit()

    result = {
        "generated": True,
        "path": str(file_path),
        "content": proposed_content,
        "status": "accepted",
    }
    store_idempotency(conn, idempotency_key, result)
    return result
