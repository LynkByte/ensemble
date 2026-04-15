"""Tests for ensemble_mcp.__main__._resolve_reports_dir auto-discovery."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from ensemble_mcp.__main__ import _resolve_reports_dir


class TestResolveReportsDirExplicit:
    """Explicit --reports-dir path provided."""

    def test_explicit_existing_dir_returns_resolved(self, tmp_path: Path) -> None:
        reports = tmp_path / "reports"
        reports.mkdir()
        result = _resolve_reports_dir(reports)
        assert result == reports.resolve()

    def test_explicit_missing_dir_returns_none(self, tmp_path: Path) -> None:
        missing = tmp_path / "no_such_dir"
        result = _resolve_reports_dir(missing)
        assert result is None

    def test_explicit_file_not_dir_returns_none(self, tmp_path: Path) -> None:
        not_a_dir = tmp_path / "reports"
        not_a_dir.write_text("data")
        result = _resolve_reports_dir(not_a_dir)
        assert result is None


class TestResolveReportsDirCwd:
    """No explicit path — falls back to CWD/reports."""

    def test_cwd_reports_dir_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        reports = tmp_path / "reports"
        reports.mkdir()
        monkeypatch.chdir(tmp_path)
        result = _resolve_reports_dir(None)
        assert result == reports.resolve()

    def test_cwd_reports_missing_falls_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When CWD/reports doesn't exist, fall through to git-root check."""
        monkeypatch.chdir(tmp_path)
        # Simulate git failure so we cleanly get None
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
            result = _resolve_reports_dir(None)
        assert result is None


class TestResolveReportsDirGitRoot:
    """No explicit path, no CWD/reports — falls back to git-root/reports."""

    def test_git_root_reports_dir_found(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        git_root = tmp_path / "project"
        git_root.mkdir()
        reports = git_root / "reports"
        reports.mkdir()

        # CWD has no reports dir
        cwd = tmp_path / "subdir"
        cwd.mkdir()
        monkeypatch.chdir(cwd)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=str(git_root) + "\n", stderr=""
            )
            result = _resolve_reports_dir(None)

        assert result == reports.resolve()

    def test_git_root_reports_missing_returns_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        git_root = tmp_path / "project"
        git_root.mkdir()
        # No reports dir under git root

        cwd = tmp_path / "subdir"
        cwd.mkdir()
        monkeypatch.chdir(cwd)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=str(git_root) + "\n", stderr=""
            )
            result = _resolve_reports_dir(None)

        assert result is None

    def test_git_not_found_returns_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = _resolve_reports_dir(None)
        assert result is None

    def test_git_timeout_returns_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=5)):
            result = _resolve_reports_dir(None)
        assert result is None

    def test_git_nonzero_exit_returns_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=128, stdout="", stderr="not a git repo"
            )
            result = _resolve_reports_dir(None)
        assert result is None


class TestResolveReportsDirPriority:
    """CWD/reports takes priority over git-root/reports."""

    def test_cwd_takes_priority_over_git_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # CWD has reports
        cwd = tmp_path / "subdir"
        cwd.mkdir()
        cwd_reports = cwd / "reports"
        cwd_reports.mkdir()

        # Git root also has reports
        git_root = tmp_path / "project"
        git_root.mkdir()
        git_reports = git_root / "reports"
        git_reports.mkdir()

        monkeypatch.chdir(cwd)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=str(git_root) + "\n", stderr=""
            )
            result = _resolve_reports_dir(None)

        # Should pick CWD/reports, not git-root/reports
        assert result == cwd_reports.resolve()
        mock_run.assert_not_called()  # git never consulted
