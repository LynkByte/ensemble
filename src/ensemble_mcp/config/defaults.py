"""Default limits, thresholds, and feature toggles.

All constants referenced by the ensemble-mcp server. Override via
layered config (settings.py) or environment variables.
"""

from __future__ import annotations

from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────
CACHE_DIR = Path.home() / ".cache" / "ensemble-mcp"
DB_PATH = CACHE_DIR / "data.db"
MODEL_DIR = CACHE_DIR / "models"
GLOBAL_CONFIG_PATH = Path.home() / ".config" / "ensemble-mcp" / "config.toml"
PROJECT_CONFIG_FILENAME = ".ensemble-mcp.toml"

# ── ONNX Embedding Model ──────────────────────────────────────────
MODEL_NAME = "all-MiniLM-L6-v2"
MODEL_URL = (
    f"https://huggingface.co/sentence-transformers/{MODEL_NAME}/resolve/main/onnx/model.onnx"
)
TOKENIZER_URL = (
    f"https://huggingface.co/sentence-transformers/{MODEL_NAME}/resolve/main/tokenizer.json"
)
EMBEDDING_DIMENSIONS = 384

# ── Pattern Memory ─────────────────────────────────────────────────
MAX_PATTERNS = 10_000
DEFAULT_TOP_K = 3
DEFAULT_MIN_SCORE = 0.3
DEFAULT_PRUNE_MAX_AGE_DAYS = 90

# ── Drift Detection ───────────────────────────────────────────────
DRIFT_THRESHOLD_ALIGNED = 0.3
DRIFT_THRESHOLD_MINOR = 0.6
# Scores >= DRIFT_THRESHOLD_MINOR are "significant_drift"

SUSPICIOUS_FILE_PATTERNS: list[str] = [
    "migration",
    "schema",
    "config",
    ".env",
    "package.json",
    "composer.json",
]
SUSPICIOUS_FILE_SIMILARITY_THRESHOLD = 0.3

# ── Skill Intelligence ────────────────────────────────────────────
CLUSTER_SIMILARITY_THRESHOLD = 0.75
DEFAULT_MIN_CLUSTER_SIZE = 3
DEFAULT_STALE_THRESHOLD_DAYS = 60

SKILL_SCAN_DIRECTORIES: list[str] = [
    ".ai/skills",
    ".claude/skills",
    ".cursor/rules",
    ".github/copilot-instructions",
    ".opencode/skills",
]

DEFAULT_SKILL_OUTPUT_DIR = ".ai/skills"

# ── Model Routing ─────────────────────────────────────────────────
MODEL_TIERS: list[str] = ["best", "mid", "cheapest"]

# ── Session / Lifecycle ───────────────────────────────────────────
SESSION_STATES: list[str] = ["pending", "running", "completed", "failed", "killed"]
STEP_STATES: list[str] = ["pending", "running", "completed", "failed", "skipped"]

# ── Idempotency ───────────────────────────────────────────────────
IDEMPOTENCY_KEY_TTL_HOURS = 24

# ── Retry Guidance ────────────────────────────────────────────────
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF_MS: list[int] = [250, 1000, 2000]

# ── Indexer ───────────────────────────────────────────────────────
INDEXER_IGNORED_DIRS: set[str] = {
    "node_modules",
    "vendor",
    ".git",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "target",
    ".tox",
    ".venv",
    "venv",
    "env",
    ".env",
}

INDEXER_IGNORED_EXTENSIONS: set[str] = {
    ".pyc",
    ".pyo",
    ".so",
    ".dylib",
    ".dll",
    ".exe",
    ".bin",
    ".wasm",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp3",
    ".mp4",
    ".avi",
    ".mov",
    ".zip",
    ".tar",
    ".gz",
    ".lock",
}

# ── Dashboard ─────────────────────────────────────────────────────
DASHBOARD_DEFAULT_PORT = 8787
DASHBOARD_HOST = "127.0.0.1"

# ── Server Metadata ───────────────────────────────────────────────
SERVER_NAME = "ensemble-mcp"
SERVER_VERSION = "0.1.0a4"
