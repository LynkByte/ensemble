"""Tests for the download progress bar in embeddings.py."""

from __future__ import annotations

import urllib.error
from http.client import HTTPResponse
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ensemble_mcp.contracts.errors import ErrorCode, ToolError
from ensemble_mcp.memory.embeddings import _download_with_progress


def _make_mock_response(data: bytes, content_length: int | None = None) -> MagicMock:
    """Create a mock HTTP response with the given data and optional Content-Length."""
    response = MagicMock(spec=HTTPResponse)
    stream = BytesIO(data)
    response.read = stream.read
    response.close = MagicMock()
    headers = MagicMock()
    headers.get = MagicMock(
        side_effect=lambda key, default=None: (
            str(content_length)
            if (key == "Content-Length" and content_length is not None)
            else default
        )
    )
    response.headers = headers
    return response


class TestDownloadWithProgress:
    def test_successful_download(self, tmp_path: Path) -> None:
        """Download should write the full content to the destination file."""
        data = b"fake model data " * 100
        dest = tmp_path / "model.onnx"
        mock_resp = _make_mock_response(data, content_length=len(data))

        with patch("ensemble_mcp.memory.embeddings.urllib.request.urlopen", return_value=mock_resp):
            _download_with_progress("https://example.com/model.onnx", dest, "Test model")

        assert dest.exists()
        assert dest.read_bytes() == data

    def test_download_without_content_length(self, tmp_path: Path) -> None:
        """Download should work even when Content-Length is missing."""
        data = b"small payload"
        dest = tmp_path / "tokenizer.json"
        mock_resp = _make_mock_response(data, content_length=None)

        with patch("ensemble_mcp.memory.embeddings.urllib.request.urlopen", return_value=mock_resp):
            _download_with_progress("https://example.com/tokenizer.json", dest, "Tokenizer")

        assert dest.exists()
        assert dest.read_bytes() == data

    def test_connection_failure_raises_tool_error(self, tmp_path: Path) -> None:
        """Connection failure should raise ToolError with IO_MODEL_DOWNLOAD."""
        dest = tmp_path / "model.onnx"

        with (
            patch(
                "ensemble_mcp.memory.embeddings.urllib.request.urlopen",
                side_effect=urllib.error.URLError("Connection refused"),
            ),
            pytest.raises(ToolError) as exc_info,
        ):
            _download_with_progress("https://example.com/model.onnx", dest, "Test model")

        assert exc_info.value.code == ErrorCode.IO_MODEL_DOWNLOAD
        assert "Failed to connect" in exc_info.value.message
        assert exc_info.value.retryable is True

    def test_download_interrupted_cleans_up(self, tmp_path: Path) -> None:
        """Interrupted download should remove the partial file."""
        dest = tmp_path / "model.onnx"

        mock_resp = MagicMock(spec=HTTPResponse)
        mock_resp.headers = MagicMock()
        mock_resp.headers.get = MagicMock(return_value="1000")
        mock_resp.read = MagicMock(side_effect=OSError("Network error"))
        mock_resp.close = MagicMock()

        with (
            patch("ensemble_mcp.memory.embeddings.urllib.request.urlopen", return_value=mock_resp),
            pytest.raises(ToolError) as exc_info,
        ):
            _download_with_progress("https://example.com/model.onnx", dest, "Test model")

        assert exc_info.value.code == ErrorCode.IO_MODEL_DOWNLOAD
        assert "interrupted" in exc_info.value.message.lower()
        # Partial file should be cleaned up
        assert not dest.exists()

    def test_error_details_contain_url_and_dest(self, tmp_path: Path) -> None:
        """Error details should include the URL and destination path."""
        dest = tmp_path / "model.onnx"

        with (
            patch(
                "ensemble_mcp.memory.embeddings.urllib.request.urlopen",
                side_effect=urllib.error.URLError("DNS failed"),
            ),
            pytest.raises(ToolError) as exc_info,
        ):
            _download_with_progress("https://example.com/model.onnx", dest, "Test model")

        assert exc_info.value.details["url"] == "https://example.com/model.onnx"
        assert str(dest) in exc_info.value.details["dest"]


class TestEnsureModel:
    def test_ensure_model_skips_when_cached(self, tmp_path: Path) -> None:
        """Should not download when model files already exist."""
        from ensemble_mcp.memory.embeddings import EmbeddingModel

        model_dir = tmp_path / "models"
        model_dir.mkdir()
        (model_dir / "model.onnx").write_bytes(b"cached")
        (model_dir / "tokenizer.json").write_bytes(b"cached")

        em = EmbeddingModel(model_dir=model_dir)

        with patch("ensemble_mcp.memory.embeddings._download_with_progress") as mock_dl:
            em._ensure_model()

        mock_dl.assert_not_called()

    def test_ensure_model_downloads_missing_model(self, tmp_path: Path) -> None:
        """Should download model when model.onnx is missing."""
        from ensemble_mcp.memory.embeddings import EmbeddingModel

        model_dir = tmp_path / "models"
        model_dir.mkdir()
        (model_dir / "tokenizer.json").write_bytes(b"cached")

        em = EmbeddingModel(model_dir=model_dir)

        with patch("ensemble_mcp.memory.embeddings._download_with_progress") as mock_dl:
            em._ensure_model()

        assert mock_dl.call_count == 1
        assert "ONNX model" in mock_dl.call_args_list[0][0][2]

    def test_ensure_model_downloads_missing_tokenizer(self, tmp_path: Path) -> None:
        """Should download tokenizer when tokenizer.json is missing."""
        from ensemble_mcp.memory.embeddings import EmbeddingModel

        model_dir = tmp_path / "models"
        model_dir.mkdir()
        (model_dir / "model.onnx").write_bytes(b"cached")

        em = EmbeddingModel(model_dir=model_dir)

        with patch("ensemble_mcp.memory.embeddings._download_with_progress") as mock_dl:
            em._ensure_model()

        assert mock_dl.call_count == 1
        assert "Tokenizer" in mock_dl.call_args_list[0][0][2]

    def test_ensure_model_downloads_both_when_missing(self, tmp_path: Path) -> None:
        """Should download both files when neither exists."""
        from ensemble_mcp.memory.embeddings import EmbeddingModel

        model_dir = tmp_path / "models"
        em = EmbeddingModel(model_dir=model_dir)

        with patch("ensemble_mcp.memory.embeddings._download_with_progress") as mock_dl:
            em._ensure_model()

        assert mock_dl.call_count == 2
