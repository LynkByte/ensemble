"""Secret/PII redaction before persistence.

Scans text for common secret patterns (API keys, tokens, passwords)
and redacts them before storing in SQLite. Runs on all text that
enters the pattern store, session checkpoints, and skill files.
"""

from __future__ import annotations

import re

# Compiled regex patterns for common secrets
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # AWS
    ("AWS Access Key", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "AWS Secret Key",
        re.compile(
            r"(?:aws_secret_access_key|secret_key)\s*[=:]\s*[A-Za-z0-9/+=]{40}",
            re.IGNORECASE,
        ),
    ),
    # Generic API keys / tokens
    (
        "API Key",
        re.compile(
            r"""(?:api[_-]?key|api[_-]?secret|access[_-]?token|auth[_-]?token|secret[_-]?key)\s*[=:]\s*["']?[A-Za-z0-9\-_.]{20,}["']?""",
            re.IGNORECASE,
        ),
    ),
    # Bearer tokens
    ("Bearer Token", re.compile(r"Bearer\s+[A-Za-z0-9\-_.~+/]+=*", re.IGNORECASE)),
    # Private keys
    (
        "Private Key",
        re.compile(
            r"-----BEGIN\s+(RSA\s+|EC\s+|DSA\s+|OPENSSH\s+)?PRIVATE\s+KEY-----",
        ),
    ),
    # Passwords in connection strings
    (
        "Password",
        re.compile(
            r"""(?:password|passwd|pwd)\s*[=:]\s*["']?[^\s"']{8,}["']?""",
            re.IGNORECASE,
        ),
    ),
    # GitHub tokens
    ("GitHub Token", re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}")),
    # Generic hex tokens (32+ chars)
    (
        "Hex Token",
        re.compile(
            r"""(?:token|secret|key)\s*[=:]\s*["']?[0-9a-f]{32,}["']?""",
            re.IGNORECASE,
        ),
    ),
    # .env style secrets
    (
        "Env Secret",
        re.compile(
            r"""(?:SECRET|TOKEN|PASSWORD|KEY|CREDENTIAL)_?[A-Z_]*\s*=\s*["']?[^\s"']{8,}["']?""",
        ),
    ),
]

REDACTED_PLACEHOLDER = "[REDACTED]"


def redact(text: str) -> str:
    """Replace detected secrets in *text* with ``[REDACTED]``.

    Returns the sanitized text. Operates on a copy — original is not
    modified.
    """
    result = text
    for _name, pattern in _SECRET_PATTERNS:
        result = pattern.sub(REDACTED_PLACEHOLDER, result)
    return result


def contains_secrets(text: str) -> bool:
    """Return ``True`` if *text* appears to contain any secret patterns."""
    return any(pattern.search(text) for _name, pattern in _SECRET_PATTERNS)
