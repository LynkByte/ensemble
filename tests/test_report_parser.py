"""Tests for _parse_bug_report_markdown() in dashboard API."""

from __future__ import annotations

from pathlib import Path

import pytest

from ensemble_mcp.dashboard.api import _parse_bug_report_markdown

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


class TestParseActualReport:
    """Test parsing the actual bug-hunter-report.md format."""

    @pytest.fixture()
    def report_text(self) -> str:
        path = REPORTS_DIR / "bug-hunter-report.md"
        if not path.exists():
            pytest.skip("bug-hunter-report.md not found")
        return path.read_text()

    @pytest.fixture()
    def parsed(self, report_text: str) -> dict:
        return _parse_bug_report_markdown(report_text)

    def test_metadata(self, parsed: dict) -> None:
        assert parsed["project"] == "ViewPulse (YouTube Analytics SaaS with AI Insights)"
        assert parsed["date"] is not None

    def test_health_score(self, parsed: dict) -> None:
        assert parsed["health_score"] == 78
        assert parsed["health_rating"] == "Moderate"

    def test_health_breakdown(self, parsed: dict) -> None:
        breakdown = parsed["health_breakdown"]
        assert len(breakdown) == 5
        pillars = {b["pillar"] for b in breakdown}
        assert "Readability" in pillars
        assert "Test Coverage" in pillars
        readability = next(b for b in breakdown if b["pillar"] == "Readability")
        assert readability["score"] == 16
        assert readability["max"] == 20
        assert readability["note"] != ""

    def test_bugs(self, parsed: dict) -> None:
        bugs = parsed["bugs"]
        assert len(bugs) == 6
        assert bugs[0]["id"] == "BH-0011"
        assert "AiContext" in bugs[0]["title"]
        assert bugs[0]["severity"] == "High"
        assert bugs[0]["cvss"] == 7.0
        assert bugs[0]["location"] != ""

    def test_smells(self, parsed: dict) -> None:
        smells = parsed["smells"]
        assert len(smells) == 10
        assert smells[0]["type"] != ""
        assert smells[0]["location"] != ""

    def test_architecture(self, parsed: dict) -> None:
        arch = parsed["architecture"]
        assert arch is not None
        assert arch["detected"] is not None
        assert "MVC" in arch["detected"]
        assert len(arch["violations"]) > 0

    def test_refactor_plan(self, parsed: dict) -> None:
        plan = parsed["refactor_plan"]
        assert len(plan) == 3
        assert plan[0]["step"] == 1
        assert plan[0]["desc"] != ""

    def test_tests(self, parsed: dict) -> None:
        tests = parsed["tests"]
        assert tests is not None
        assert tests["passed"] == 848
        assert tests["failed"] == 0
        assert tests["duration_sec"] == 55.32

    def test_ci(self, parsed: dict) -> None:
        ci = parsed["ci"]
        assert ci is not None
        assert ci["status"] == "PASS"
        assert len(ci["checks"]) == 4
        assert ci["checks"][0]["ok"] is True

    def test_security(self, parsed: dict) -> None:
        security = parsed["security"]
        assert len(security) == 0


class TestParseOldFormat:
    """Test backward compatibility with the old report format."""

    OLD_FORMAT = """\
# Bug Report

**Project:** my-project
**Date:** 2026-01-01
**Analyzer:** bug-hunter v1
**Branch:** main
**Commit:** abc123

---

## Overall Health Score: 75/100 (Fair)

| Dimension | Score | Max |
|-----------|-------|-----|
| Readability | 15 | 20 |
| Maintainability | 12 | 20 |

---

## Bugs Found

### B1: Some bug title
- **Severity:** High (CVSS 7.5)
- **Category:** Security
- **Location:** `src/foo.py:10`
- **Description:** A bad thing happens.
- **Fix:** Do the right thing.

### B2: Another bug
- **Severity:** Low (CVSS 2.0)
- **Location:** `src/bar.py:20`
- **Description:** Minor issue.
- **Fix:** Fix it.

---

## Code Smells

### S1: Bad naming
- **Location:** `src/foo.py:5`
- **Fix:** Rename variables.

---

## Architecture

### Detected: Monolith

### Architecture Issues
1. **Circular dependency** between modules

### Recommended Improvements
- Split into microservices

---

## Refactor Plan

| Priority | Item | Complexity | Impact |
|----------|------|------------|--------|
| 1 | **Split modules** — reduce coupling | Medium | High |

---

## Test Results

42 passed, 3 failed, 1 skipped (5.2s)

---

## CI/CD Quality Gate

CI Status: FAIL

| Gate | Threshold | Value | Status |
|------|-----------|-------|--------|
| Health | >= 80 | 75 | FAIL |
| Tests | 100% | 93% | FAIL |

---

## Security Audit

| Check | Status | Notes |
|-------|--------|-------|
| SQL injection | **Safe** | Parameterized queries |

---
"""

    @pytest.fixture()
    def parsed(self) -> dict:
        return _parse_bug_report_markdown(self.OLD_FORMAT)

    def test_metadata(self, parsed: dict) -> None:
        assert parsed["project"] == "my-project"
        assert parsed["analyzer"] == "bug-hunter v1"
        assert parsed["branch"] == "main"
        assert parsed["commit"] == "abc123"

    def test_health_score(self, parsed: dict) -> None:
        assert parsed["health_score"] == 75
        assert parsed["health_rating"] == "Fair"

    def test_health_breakdown(self, parsed: dict) -> None:
        breakdown = parsed["health_breakdown"]
        assert len(breakdown) == 2
        assert breakdown[0]["pillar"] == "Readability"
        assert breakdown[0]["score"] == 15
        assert breakdown[0]["max"] == 20

    def test_bugs(self, parsed: dict) -> None:
        bugs = parsed["bugs"]
        assert len(bugs) == 2
        assert bugs[0]["severity"] == "High"
        assert bugs[0]["cvss"] == 7.5
        assert bugs[0]["category"] == "Security"

    def test_smells(self, parsed: dict) -> None:
        smells = parsed["smells"]
        assert len(smells) == 1

    def test_architecture(self, parsed: dict) -> None:
        arch = parsed["architecture"]
        assert arch is not None
        assert arch["detected"] == "Monolith"
        assert len(arch["violations"]) == 1
        assert "Circular" in arch["violations"][0]
        assert len(arch["recommendations"]) == 1

    def test_refactor_plan(self, parsed: dict) -> None:
        plan = parsed["refactor_plan"]
        assert len(plan) == 1
        assert plan[0]["title"] == "Split modules"
        assert plan[0]["effort"] == "Medium"
        assert plan[0]["impact"] == "High"

    def test_tests(self, parsed: dict) -> None:
        tests = parsed["tests"]
        assert tests is not None
        assert tests["passed"] == 42
        assert tests["failed"] == 3
        assert tests["skipped"] == 1
        assert tests["duration_sec"] == 5.2

    def test_ci(self, parsed: dict) -> None:
        ci = parsed["ci"]
        assert ci is not None
        assert ci["status"] == "FAIL"
        assert len(ci["checks"]) == 2
        assert not ci["checks"][0]["ok"]

    def test_security(self, parsed: dict) -> None:
        security = parsed["security"]
        assert len(security) == 1
        assert security[0]["check"] == "SQL injection"


class TestParseEmptyInput:
    """Edge case: empty or minimal input returns safe defaults."""

    def test_empty_string(self) -> None:
        result = _parse_bug_report_markdown("")
        assert result["bugs"] == []
        assert result["smells"] == []
        assert result["health_score"] is None
        assert result["ci"] is None
        assert result["tests"] is None
