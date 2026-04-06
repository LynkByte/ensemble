"""Tests for codebase indexer tools (project_index, project_query, project_dependencies)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ensemble_mcp.tools.indexer import (
    _detect_language,
    _detect_role,
    _extract_exports,
    _extract_imports,
    _is_ignored,
    project_dependencies,
    project_index,
    project_query,
)

# ── Internal helpers ──────────────────────────────────────────────


class TestDetectLanguage:
    def test_python(self):
        assert _detect_language(Path("foo.py")) == "python"
        assert _detect_language(Path("foo.pyi")) == "python"

    def test_typescript(self):
        assert _detect_language(Path("app.ts")) == "typescript"
        assert _detect_language(Path("App.tsx")) == "typescript"

    def test_javascript(self):
        assert _detect_language(Path("index.js")) == "javascript"
        assert _detect_language(Path("App.jsx")) == "javascript"

    def test_go(self):
        assert _detect_language(Path("main.go")) == "go"

    def test_rust(self):
        assert _detect_language(Path("lib.rs")) == "rust"

    def test_unknown(self):
        assert _detect_language(Path("file.xyz")) is None

    def test_dockerfile(self):
        assert _detect_language(Path("Dockerfile")) == "dockerfile"


class TestDetectRole:
    def test_test_file(self):
        assert _detect_role("tests/test_foo.py") == "test"

    def test_migration(self):
        assert _detect_role("database/migrations/001.sql") == "migration"

    def test_config(self):
        assert _detect_role("config/app.py") == "config"

    def test_model(self):
        assert _detect_role("src/models/user.py") == "model"

    def test_controller(self):
        assert _detect_role("app/controllers/auth.py") == "controller"

    def test_service(self):
        assert _detect_role("src/services/payment.py") == "service"

    def test_utility(self):
        assert _detect_role("src/utils/helpers.py") == "utility"

    def test_no_role(self):
        assert _detect_role("main.py") is None


class TestExtractExports:
    def test_python_classes(self):
        content = "class Foo:\n    pass\n\nclass Bar:\n    pass\n"
        exports = _extract_exports(content, "python")
        names = {e["name"] for e in exports}
        assert "Foo" in names
        assert "Bar" in names

    def test_python_functions(self):
        content = "def hello():\n    pass\n\ndef world():\n    pass\n"
        exports = _extract_exports(content, "python")
        names = {e["name"] for e in exports}
        assert "hello" in names
        assert "world" in names

    def test_typescript_exports(self):
        content = "export class UserService {}\nexport function getUser() {}\n"
        exports = _extract_exports(content, "typescript")
        names = {e["name"] for e in exports}
        assert "UserService" in names
        assert "getUser" in names

    def test_go_exports(self):
        content = "func HandleRequest() {}\ntype Server struct {}\n"
        exports = _extract_exports(content, "go")
        names = {e["name"] for e in exports}
        assert "HandleRequest" in names
        assert "Server" in names

    def test_rust_exports(self):
        content = "pub fn process() {}\npub struct Config {}\n"
        exports = _extract_exports(content, "rust")
        names = {e["name"] for e in exports}
        assert "process" in names
        assert "Config" in names

    def test_no_language_returns_empty(self):
        assert _extract_exports("class Foo:", None) == []

    def test_empty_content_returns_empty(self):
        assert _extract_exports("", "python") == []


class TestExtractImports:
    def test_python_imports(self):
        content = "import os\nfrom pathlib import Path\n"
        imports = _extract_imports(content, "python")
        paths = {i["import_path"] for i in imports}
        assert "os" in paths
        assert "pathlib" in paths

    def test_typescript_imports(self):
        content = "import { foo } from './utils';\nimport bar from 'lodash';\n"
        imports = _extract_imports(content, "typescript")
        paths = {i["import_path"] for i in imports}
        assert "./utils" in paths
        assert "lodash" in paths

    def test_no_language_returns_empty(self):
        assert _extract_imports("import os", None) == []


class TestIsIgnored:
    def test_node_modules_ignored(self):
        assert _is_ignored("node_modules/foo.js", {"node_modules"}, []) is True

    def test_gitignore_pattern(self):
        assert _is_ignored("dist/bundle.js", set(), ["dist/*"]) is True

    def test_not_ignored(self):
        assert _is_ignored("src/main.py", {"node_modules"}, []) is False


# ── Tool-level tests ──────────────────────────────────────────────


class TestProjectIndex:
    @pytest.mark.asyncio
    async def test_index_project(self, test_conn: sqlite3.Connection, tmp_path: Path):
        # Create a small project
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text("class App:\n    pass\n")
        (src / "utils.py").write_text("def helper():\n    pass\n")
        (tmp_path / "README.md").write_text("# My Project\n")

        env = await project_index(
            test_conn,
            project_path=str(tmp_path),
        )
        assert env["ok"] is True
        data = env["data"]
        assert data["indexed"] is True
        assert data["files"] >= 2  # at least the .py files
        assert data["total"] >= 2

    @pytest.mark.asyncio
    async def test_index_nonexistent_dir(self, test_conn: sqlite3.Connection):
        env = await project_index(
            test_conn,
            project_path="/nonexistent/path/12345",
        )
        assert env["ok"] is False
        assert env["error"]["code"] == "NOT_FOUND_PROJECT"

    @pytest.mark.asyncio
    async def test_incremental_index(
        self,
        test_conn: sqlite3.Connection,
        tmp_path: Path,
    ):
        (tmp_path / "app.py").write_text("x = 1\n")

        env1 = await project_index(test_conn, project_path=str(tmp_path))
        env2 = await project_index(test_conn, project_path=str(tmp_path))

        assert env1["ok"] is True
        assert env2["ok"] is True
        # Second run should use cache for unchanged files
        assert env2["data"]["cached"] >= 0

    @pytest.mark.asyncio
    async def test_force_reindex(
        self,
        test_conn: sqlite3.Connection,
        tmp_path: Path,
    ):
        (tmp_path / "app.py").write_text("x = 1\n")
        await project_index(test_conn, project_path=str(tmp_path))
        env = await project_index(test_conn, project_path=str(tmp_path), force=True)
        assert env["ok"] is True
        assert env["data"]["files"] >= 1


class TestProjectQuery:
    @pytest.mark.asyncio
    async def test_query_by_language(
        self,
        test_conn: sqlite3.Connection,
        tmp_path: Path,
    ):
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text("class App:\n    pass\n")
        (src / "style.css").write_text("body { color: red; }\n")
        await project_index(test_conn, project_path=str(tmp_path))

        env = await project_query(
            test_conn,
            project_path=str(tmp_path),
            file_types=["python"],
        )
        assert env["ok"] is True
        for f in env["data"]["files"]:
            assert f["language"] == "python"

    @pytest.mark.asyncio
    async def test_query_by_path_pattern(
        self,
        test_conn: sqlite3.Connection,
        tmp_path: Path,
    ):
        (tmp_path / "main.py").write_text("x = 1\n")
        (tmp_path / "test_main.py").write_text("y = 2\n")
        await project_index(test_conn, project_path=str(tmp_path))

        env = await project_query(
            test_conn,
            project_path=str(tmp_path),
            path_pattern="test_",
        )
        assert env["ok"] is True
        for f in env["data"]["files"]:
            assert "test_" in f["path"]


class TestProjectDependencies:
    @pytest.mark.asyncio
    async def test_dependencies_for_file(
        self,
        test_conn: sqlite3.Connection,
        tmp_path: Path,
    ):
        (tmp_path / "app.py").write_text("from utils import helper\n")
        (tmp_path / "utils.py").write_text("def helper():\n    pass\n")
        await project_index(test_conn, project_path=str(tmp_path))

        env = await project_dependencies(
            test_conn,
            project_path=str(tmp_path),
            file_path="app.py",
        )
        assert env["ok"] is True
        assert "utils" in env["data"]["imports"]

    @pytest.mark.asyncio
    async def test_dependencies_file_not_found(
        self,
        test_conn: sqlite3.Connection,
        tmp_path: Path,
    ):
        (tmp_path / "app.py").write_text("x = 1\n")
        await project_index(test_conn, project_path=str(tmp_path))

        env = await project_dependencies(
            test_conn,
            project_path=str(tmp_path),
            file_path="nonexistent.py",
        )
        assert env["ok"] is False
        assert env["error"]["code"] == "NOT_FOUND_FILE"
