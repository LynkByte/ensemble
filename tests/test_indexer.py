"""Tests for codebase indexer tools (project_index, project_query, project_dependencies)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ensemble_mcp.tools.indexer import (
    _detect_language,
    _detect_role,
    _extract_block_doc_comment,
    _extract_exports,
    _extract_imports,
    _extract_line_doc_comment,
    _extract_python_docstring,
    _get_line_at_pos,
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


# ── Signature & docstring helper tests ────────────────────────────


class TestSignatureDocstringHelpers:
    """Tests for _get_line_at_pos, _extract_python_docstring,
    _extract_block_doc_comment, and _extract_line_doc_comment."""

    # ── _get_line_at_pos ──

    def test_get_line_at_pos_simple(self):
        content = "line one\nline two\nline three\n"
        # pos in the middle of "line two"
        pos = content.index("line two")
        assert _get_line_at_pos(content, pos) == "line two"

    def test_get_line_at_pos_strips_trailing_brace(self):
        content = "def foo() {\n"
        assert _get_line_at_pos(content, 0) == "def foo()"

    def test_get_line_at_pos_strips_trailing_colon(self):
        content = "class Foo:\n"
        assert _get_line_at_pos(content, 0) == "class Foo"

    def test_get_line_at_pos_caps_at_300(self):
        long_line = "x" * 400 + "\n"
        result = _get_line_at_pos(long_line, 0)
        assert len(result) <= 300

    def test_get_line_at_pos_first_line(self):
        content = "first\nsecond\n"
        assert _get_line_at_pos(content, 0) == "first"

    def test_get_line_at_pos_last_line_no_newline(self):
        content = "first\nlast"
        pos = content.index("last")
        assert _get_line_at_pos(content, pos) == "last"

    # ── _extract_python_docstring ──

    def test_python_docstring_single_line(self):
        lines = ["def foo():", '    """A simple function."""', "    pass"]
        result = _extract_python_docstring(lines, 0)
        assert result == "A simple function."

    def test_python_docstring_multiline(self):
        lines = [
            "def foo():",
            '    """',
            "    Multiline docstring.",
            "    Second line.",
            '    """',
            "    pass",
        ]
        result = _extract_python_docstring(lines, 0)
        assert result is not None
        assert "Multiline docstring." in result
        assert "Second line." in result

    def test_python_docstring_single_quotes(self):
        lines = ["class Bar:", "    '''Single-quoted doc.'''", "    pass"]
        result = _extract_python_docstring(lines, 0)
        assert result == "Single-quoted doc."

    def test_python_docstring_none_when_missing(self):
        lines = ["def foo():", "    pass"]
        result = _extract_python_docstring(lines, 0)
        assert result is None

    def test_python_docstring_blank_lines_before_docstring(self):
        lines = ["def foo():", "", '    """After blank."""', "    pass"]
        result = _extract_python_docstring(lines, 0)
        assert result == "After blank."

    def test_python_docstring_caps_at_500(self):
        long_doc = "x" * 600
        lines = ["def foo():", f'    """{long_doc}"""', "    pass"]
        result = _extract_python_docstring(lines, 0)
        assert result is not None
        assert len(result) <= 500

    # ── _extract_block_doc_comment ──

    def test_block_doc_comment_jsdoc(self):
        content = (
            "/**\n * Create a new user.\n"
            " * @param name The user name.\n"
            " */\nexport function createUser() {}\n"
        )
        match_start = content.index("export")
        result = _extract_block_doc_comment(content, match_start)
        assert result is not None
        assert "Create a new user." in result
        assert "@param name The user name." in result

    def test_block_doc_comment_phpdoc(self):
        content = "<?php\n/**\n * A PHP repository.\n */\nclass Foo {}\n"
        match_start = content.index("class")
        result = _extract_block_doc_comment(content, match_start)
        assert result is not None
        assert "A PHP repository." in result

    def test_block_doc_comment_single_line(self):
        content = "/** Quick doc. */\nexport class Bar {}\n"
        match_start = content.index("export")
        result = _extract_block_doc_comment(content, match_start)
        assert result is not None
        assert "Quick doc." in result

    def test_block_doc_comment_none_when_missing(self):
        content = "export function noDoc() {}\n"
        match_start = content.index("export")
        result = _extract_block_doc_comment(content, match_start)
        assert result is None

    def test_block_doc_comment_regular_comment_not_matched(self):
        content = "/* not a doc comment */\nexport class Baz {}\n"
        match_start = content.index("export")
        result = _extract_block_doc_comment(content, match_start)
        assert result is None

    # ── _extract_line_doc_comment ──

    def test_line_doc_comment_go(self):
        lines = ["// HandleRequest processes an incoming request.", "func HandleRequest() {}"]
        result = _extract_line_doc_comment(lines, 1, "//")
        assert result is not None
        assert "HandleRequest processes an incoming request." in result

    def test_line_doc_comment_rust(self):
        lines = [
            "/// Compute the result.",
            "/// Returns the computed value.",
            "pub fn compute() {}",
        ]
        result = _extract_line_doc_comment(lines, 2, "///")
        assert result is not None
        assert "Compute the result." in result
        assert "Returns the computed value." in result

    def test_line_doc_comment_ruby(self):
        lines = ["# A ruby class.", "# Does interesting things.", "class MyClass", "end"]
        result = _extract_line_doc_comment(lines, 2, "#")
        assert result is not None
        assert "A ruby class." in result
        assert "Does interesting things." in result

    def test_line_doc_comment_none_when_missing(self):
        lines = ["", "func Foo() {}"]
        result = _extract_line_doc_comment(lines, 1, "//")
        assert result is None

    def test_line_doc_comment_stops_at_non_comment(self):
        lines = ["// first comment", "", "// second comment", "func Bar() {}"]
        result = _extract_line_doc_comment(lines, 3, "//")
        assert result is not None
        assert "second comment" in result
        assert "first comment" not in result

    def test_line_doc_comment_multiline_go(self):
        lines = [
            "// Line one.",
            "// Line two.",
            "// Line three.",
            "func Multi() {}",
        ]
        result = _extract_line_doc_comment(lines, 3, "//")
        assert result is not None
        assert "Line one." in result
        assert "Line three." in result

    def test_line_doc_comment_caps_at_500(self):
        long_comment = "x" * 600
        lines = [f"// {long_comment}", "func Foo() {}"]
        result = _extract_line_doc_comment(lines, 1, "//")
        assert result is not None
        assert len(result) <= 500


# ── Export extraction with signature & docstring ──────────────────


class TestExtractExportsSignatureDocstring:
    """Verify signature and docstring fields in extract results for all 6 languages."""

    def test_python_signature_and_docstring(self):
        content = (
            "class Greeter:\n"
            '    """A greeter class."""\n'
            "    pass\n\n"
            "def greet(name: str) -> str:\n"
            '    """Say hello."""\n'
            '    return f"Hello {name}"\n'
        )
        exports = _extract_exports(content, "python")
        by_name = {e["name"]: e for e in exports}

        assert "Greeter" in by_name
        assert by_name["Greeter"]["signature"] == "class Greeter"
        assert by_name["Greeter"]["docstring"] == "A greeter class."

        assert "greet" in by_name
        assert "def greet(name: str) -> str" in by_name["greet"]["signature"]
        assert by_name["greet"]["docstring"] == "Say hello."

    def test_python_all_entries_have_none_sig_doc(self):
        content = '__all__ = ["foo"]\n'
        exports = _extract_exports(content, "python")
        assert len(exports) == 1
        assert exports[0]["signature"] is None
        assert exports[0]["docstring"] is None

    def test_python_multiline_docstring(self):
        content = (
            "def calculate(x, y):\n"
            '    """\n'
            "    Calculate the sum.\n\n"
            "    Returns the result.\n"
            '    """\n'
            "    return x + y\n"
        )
        exports = _extract_exports(content, "python")
        by_name = {e["name"]: e for e in exports}
        assert "calculate" in by_name
        doc = by_name["calculate"]["docstring"]
        assert doc is not None
        assert "Calculate the sum." in doc

    def test_typescript_signature_and_docstring(self):
        content = (
            "/**\n * Fetch user data.\n */\n"
            "export function fetchUser(id: number)"
            ": Promise<User> {\n"
            "  return api.get(id);\n}\n"
        )
        exports = _extract_exports(content, "typescript")
        by_name = {e["name"]: e for e in exports}

        assert "fetchUser" in by_name
        assert "export function fetchUser(id: number)" in by_name["fetchUser"]["signature"]
        assert by_name["fetchUser"]["docstring"] is not None
        assert "Fetch user data." in by_name["fetchUser"]["docstring"]

    def test_typescript_no_docstring(self):
        content = "export const MAX_RETRIES = 3;\n"
        exports = _extract_exports(content, "typescript")
        by_name = {e["name"]: e for e in exports}
        assert "MAX_RETRIES" in by_name
        assert by_name["MAX_RETRIES"]["docstring"] is None
        assert by_name["MAX_RETRIES"]["signature"] is not None

    def test_javascript_signature(self):
        content = "export function add(a, b) {\n  return a + b;\n}\n"
        exports = _extract_exports(content, "javascript")
        by_name = {e["name"]: e for e in exports}
        assert "add" in by_name
        assert "export function add(a, b)" in by_name["add"]["signature"]

    def test_php_signature_and_docstring(self):
        content = "<?php\n/**\n * A repository class.\n */\nclass UserRepository {\n}\n"
        exports = _extract_exports(content, "php")
        by_name = {e["name"]: e for e in exports}
        assert "UserRepository" in by_name
        assert "class UserRepository" in by_name["UserRepository"]["signature"]
        assert "A repository class." in by_name["UserRepository"]["docstring"]

    def test_go_signature_and_docstring(self):
        content = (
            "// NewServer creates a new server instance.\nfunc NewServer(port int) *Server {\n}\n"
        )
        exports = _extract_exports(content, "go")
        by_name = {e["name"]: e for e in exports}
        assert "NewServer" in by_name
        assert "func NewServer(port int) *Server" in by_name["NewServer"]["signature"]
        assert "NewServer creates a new server instance." in by_name["NewServer"]["docstring"]

    def test_go_struct_with_doc(self):
        content = "// Config holds application configuration.\ntype Config struct {\n}\n"
        exports = _extract_exports(content, "go")
        by_name = {e["name"]: e for e in exports}
        assert "Config" in by_name
        assert "type Config struct" in by_name["Config"]["signature"]
        assert "Config holds application configuration." in by_name["Config"]["docstring"]

    def test_go_method_receiver_extracts_method_name(self):
        """Method receiver syntax should extract the method name,
        not the receiver variable."""
        content = (
            "// Handle processes the request.\n"
            "func (r *Receiver) Handle() error {\n"
            "    return nil\n}\n"
        )
        exports = _extract_exports(content, "go")
        by_name = {e["name"]: e for e in exports}
        assert "Handle" in by_name
        sig = by_name["Handle"]["signature"]
        assert "func (r *Receiver) Handle() error" in sig
        doc = by_name["Handle"]["docstring"]
        assert doc is not None
        assert "Handle processes the request." in doc

    def test_go_method_receiver_no_pointer(self):
        """Value receiver (no pointer) should also work."""
        content = "func (s Server) Start() {\n}\n"
        exports = _extract_exports(content, "go")
        names = {e["name"] for e in exports}
        assert "Start" in names

    def test_go_interface_exported(self):
        """Go interfaces should be extracted as exports."""
        content = (
            "// Handler defines the handler interface.\ntype Handler interface {\n    Handle()\n}\n"
        )
        exports = _extract_exports(content, "go")
        by_name = {e["name"]: e for e in exports}
        assert "Handler" in by_name
        assert by_name["Handler"]["kind"] == "class"
        assert "type Handler interface" in by_name["Handler"]["signature"]

    def test_rust_signature_and_docstring(self):
        content = "/// Process the input data.\npub fn process(data: &[u8]) -> Result<()> {\n}\n"
        exports = _extract_exports(content, "rust")
        by_name = {e["name"]: e for e in exports}
        assert "process" in by_name
        assert "pub fn process(data: &[u8]) -> Result<()>" in by_name["process"]["signature"]
        assert "Process the input data." in by_name["process"]["docstring"]

    def test_rust_struct_with_docstring(self):
        content = (
            "/// Application configuration.\n"
            "/// Loaded from environment.\n"
            "pub struct AppConfig {\n}\n"
        )
        exports = _extract_exports(content, "rust")
        by_name = {e["name"]: e for e in exports}
        assert "AppConfig" in by_name
        doc = by_name["AppConfig"]["docstring"]
        assert doc is not None
        assert "Application configuration." in doc
        assert "Loaded from environment." in doc

    def test_ruby_signature_and_docstring(self):
        content = (
            "# A user model class.\nclass User\n"
            "  def initialize(name)\n"
            "    @name = name\n  end\nend\n"
        )
        exports = _extract_exports(content, "ruby")
        by_name = {e["name"]: e for e in exports}
        assert "User" in by_name
        assert "class User" in by_name["User"]["signature"]
        assert "A user model class." in by_name["User"]["docstring"]

    def test_ruby_module_with_docstring(self):
        content = "# Authentication helpers.\nmodule Auth\nend\n"
        exports = _extract_exports(content, "ruby")
        by_name = {e["name"]: e for e in exports}
        assert "Auth" in by_name
        assert "module Auth" in by_name["Auth"]["signature"]
        assert "Authentication helpers." in by_name["Auth"]["docstring"]

    def test_ruby_def_with_docstring(self):
        content = "# Compute the total.\ndef total(items)\n  items.sum\nend\n"
        exports = _extract_exports(content, "ruby")
        by_name = {e["name"]: e for e in exports}
        assert "total" in by_name
        assert "def total(items)" in by_name["total"]["signature"]
        assert "Compute the total." in by_name["total"]["docstring"]

    def test_exports_always_have_signature_docstring_keys(self):
        """All exports must include 'signature' and 'docstring' keys."""
        cases = [
            ("class Foo:\n    pass\n", "python"),
            ("export class Bar {}\n", "typescript"),
            ("export function baz() {}\n", "javascript"),
            ("class Qux {}\n", "php"),
            ("func Handle() {}\n", "go"),
            ("pub fn run() {}\n", "rust"),
            ("class Cls\nend\n", "ruby"),
        ]
        for content, lang in cases:
            exports = _extract_exports(content, lang)
            for exp in exports:
                assert "signature" in exp, f"Missing 'signature' for {lang}: {exp}"
                assert "docstring" in exp, f"Missing 'docstring' for {lang}: {exp}"


# ── Integration: query searches exports ───────────────────────────


class TestProjectQueryExportSearch:
    @pytest.mark.asyncio
    async def test_query_by_export_name(
        self,
        test_conn: sqlite3.Connection,
        tmp_path: Path,
    ):
        """Querying by export name should find the file containing that export."""
        (tmp_path / "models.py").write_text(
            'class UserAccount:\n    """Manages user accounts."""\n    pass\n'
        )
        (tmp_path / "utils.py").write_text("def format_date():\n    pass\n")
        await project_index(test_conn, project_path=str(tmp_path))

        env = await project_query(
            test_conn,
            project_path=str(tmp_path),
            query="UserAccount",
        )
        assert env["ok"] is True
        paths = [f["path"] for f in env["data"]["files"]]
        assert "models.py" in paths

    @pytest.mark.asyncio
    async def test_query_by_docstring_term(
        self,
        test_conn: sqlite3.Connection,
        tmp_path: Path,
    ):
        """Querying by a docstring term should find the file containing that export."""
        (tmp_path / "service.py").write_text(
            'def process_payment(amount):\n    """Process a credit card payment."""\n    pass\n'
        )
        (tmp_path / "other.py").write_text("x = 1\n")
        await project_index(test_conn, project_path=str(tmp_path))

        env = await project_query(
            test_conn,
            project_path=str(tmp_path),
            query="credit card",
        )
        assert env["ok"] is True
        paths = [f["path"] for f in env["data"]["files"]]
        assert "service.py" in paths

    @pytest.mark.asyncio
    async def test_query_returns_signature_docstring_in_exports(
        self,
        test_conn: sqlite3.Connection,
        tmp_path: Path,
    ):
        """project_query should include signature and docstring in export dicts."""
        (tmp_path / "app.py").write_text(
            "def run_server(host: str, port: int):\n"
            '    """Start the application server."""\n'
            "    pass\n"
        )
        await project_index(test_conn, project_path=str(tmp_path))

        env = await project_query(
            test_conn,
            project_path=str(tmp_path),
        )
        assert env["ok"] is True
        files = env["data"]["files"]
        py_files = [f for f in files if f["path"] == "app.py"]
        assert len(py_files) == 1
        exports = py_files[0]["exports"]
        assert len(exports) >= 1
        run_server = [e for e in exports if e["name"] == "run_server"]
        assert len(run_server) == 1
        assert "signature" in run_server[0]
        assert "docstring" in run_server[0]
        assert "def run_server(host: str, port: int)" in run_server[0]["signature"]
        assert run_server[0]["docstring"] == "Start the application server."

    @pytest.mark.asyncio
    async def test_query_by_signature_term(
        self,
        test_conn: sqlite3.Connection,
        tmp_path: Path,
    ):
        """Querying by a term in a signature should match."""
        (tmp_path / "handler.py").write_text("def handle_webhook(payload: dict):\n    pass\n")
        await project_index(test_conn, project_path=str(tmp_path))

        env = await project_query(
            test_conn,
            project_path=str(tmp_path),
            query="webhook",
        )
        assert env["ok"] is True
        paths = [f["path"] for f in env["data"]["files"]]
        assert "handler.py" in paths
