"""SQLite/file lock helpers for concurrent access safety.

Ensures WAL mode is enabled and provides an advisory lock context
manager for operations that need exclusive access.
"""

from __future__ import annotations

import fcntl
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


def enable_wal(conn: sqlite3.Connection) -> None:
    """Enable WAL journal mode for concurrent read/write access."""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Create a new SQLite connection with WAL mode and recommended pragmas."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    enable_wal(conn)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def advisory_lock(lock_path: Path) -> Generator[None, None, None]:
    """File-based advisory lock for operations needing exclusive access.

    Usage::

        with advisory_lock(Path("/tmp/ensemble-mcp.lock")):
            # exclusive operation
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = open(lock_path, "w")  # noqa: SIM115
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()
