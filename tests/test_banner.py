"""Tests for the startup banner."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from ensemble_mcp.cli.banner import print_banner


class TestPrintBanner:
    def test_banner_prints_server_name(self) -> None:
        buf = StringIO()
        with patch("ensemble_mcp.cli.banner._stderr") as mock_console:
            mock_console.print = lambda *a, **kw: buf.write(" ".join(str(x) for x in a) + "\n")
            print_banner()

        output = buf.getvalue()
        assert "ensemble-mcp" in output

    def test_banner_prints_version(self) -> None:
        buf = StringIO()
        with patch("ensemble_mcp.cli.banner._stderr") as mock_console:
            mock_console.print = lambda *a, **kw: buf.write(" ".join(str(x) for x in a) + "\n")
            print_banner()

        output = buf.getvalue()
        assert "v0.1.0" in output

    def test_banner_prints_paths(self) -> None:
        buf = StringIO()
        with patch("ensemble_mcp.cli.banner._stderr") as mock_console:
            mock_console.print = lambda *a, **kw: buf.write(" ".join(str(x) for x in a) + "\n")
            print_banner()

        output = buf.getvalue()
        assert "Config:" in output
        assert "Database:" in output
        assert "Models:" in output

    def test_banner_prints_ready_message(self) -> None:
        buf = StringIO()
        with patch("ensemble_mcp.cli.banner._stderr") as mock_console:
            mock_console.print = lambda *a, **kw: buf.write(" ".join(str(x) for x in a) + "\n")
            print_banner()

        output = buf.getvalue()
        assert "Server started" in output
        assert "stdio" in output
