"""Tests for PyCraft Phase 3 restricted workspace tools and endpoints."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.workspace import (
    MAX_FILE_SIZE_BYTES,
    get_workspace_root,
    list_workspace_files,
    read_workspace_file,
    validate_and_resolve_path,
)


class WorkspaceToolTests(unittest.TestCase):
    """Test suite for workspace isolation, listing, and reading safeguards."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        # Create an isolated temporary workspace for tests
        self.test_dir = tempfile.mkdtemp(prefix="pycraft_test_ws_")
        self.ws_root = Path(self.test_dir).resolve()

        # Populate temporary workspace with test files
        (self.ws_root / "sample.txt").write_text("Hello from PyCraft workspace!", encoding="utf-8")
        (self.ws_root / "subfolder").mkdir(parents=True, exist_ok=True)
        (self.ws_root / "subfolder" / "nested.txt").write_text("Nested content", encoding="utf-8")

        # Excluded files and directories
        (self.ws_root / ".env").write_text("SECRET=12345", encoding="utf-8")
        (self.ws_root / ".git").mkdir(parents=True, exist_ok=True)
        (self.ws_root / ".git" / "config").write_text("[core]", encoding="utf-8")
        (self.ws_root / "__pycache__").mkdir(parents=True, exist_ok=True)
        (self.ws_root / "__pycache__" / "temp.pyc").write_bytes(b"\x00\x01\x02")
        (self.ws_root / "credentials.json").write_text('{"token": "xyz"}', encoding="utf-8")
        (self.ws_root / "binary.bin").write_bytes(b"\x00\xff\xfe\x00data")
        (self.ws_root / "corrupt_binary.txt").write_bytes(b"hello\x00world")
        (self.ws_root / "invalid_utf8.txt").write_bytes(b"hello\xff\xfe\xfa")

        # Create oversized file (>100 KB)
        oversized_data = "A" * (MAX_FILE_SIZE_BYTES + 1024)
        (self.ws_root / "oversized.txt").write_text(oversized_data, encoding="utf-8")

        # Patch environment to point to our test workspace
        self.orig_env = os.environ.get("PYCRAFT_WORKSPACE")
        os.environ["PYCRAFT_WORKSPACE"] = str(self.ws_root)

    def tearDown(self):
        # Restore environment
        if self.orig_env is not None:
            os.environ["PYCRAFT_WORKSPACE"] = self.orig_env
        else:
            os.environ.pop("PYCRAFT_WORKSPACE", None)

        # Cleanup temporary directory
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_workspace_listing_excludes_sensitive_and_binary(self):
        """Listing workspace should only return allowed relative text files."""
        files = list_workspace_files(self.ws_root)
        self.assertIn("sample.txt", files)
        self.assertIn("subfolder/nested.txt", files)
        self.assertNotIn(".env", files)
        self.assertNotIn(".git/config", files)
        self.assertNotIn("__pycache__/temp.pyc", files)
        self.assertNotIn("credentials.json", files)
        self.assertNotIn("binary.bin", files)
        self.assertNotIn("oversized.txt", files)

    def test_read_valid_utf8_file(self):
        """Reading an allowed UTF-8 file should succeed with content and size."""
        path, content, size = read_workspace_file("sample.txt", self.ws_root)
        self.assertEqual(path, "sample.txt")
        self.assertEqual(content, "Hello from PyCraft workspace!")
        self.assertGreater(size, 0)

    def test_read_nested_file(self):
        """Reading nested file via relative path should succeed."""
        path, content, size = read_workspace_file("subfolder/nested.txt", self.ws_root)
        self.assertEqual(path, "subfolder/nested.txt")
        self.assertEqual(content, "Nested content")

    def test_path_traversal_blocked(self):
        """Directory traversal attempts with .. must be rejected."""
        with self.assertRaises(ValueError) as ctx:
            read_workspace_file("../outside.txt", self.ws_root)
        self.assertIn("traversal", str(ctx.exception).lower())

        with self.assertRaises(ValueError) as ctx2:
            read_workspace_file("subfolder/../../outside.txt", self.ws_root)
        self.assertIn("traversal", str(ctx2.exception).lower())

    def test_symlink_escape_blocked(self):
        """Symlinks pointing outside the workspace must be rejected."""
        outside_file = self.ws_root.parent / "secret_outside.txt"
        outside_file.write_text("SUPER_SECRET", encoding="utf-8")
        try:
            symlink_path = self.ws_root / "escape_link.txt"
            try:
                symlink_path.symlink_to(outside_file)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks not supported without admin privileges on Windows.")

            with self.assertRaises(PermissionError) as ctx:
                read_workspace_file("escape_link.txt", self.ws_root)
            self.assertIn("workspace boundary", str(ctx.exception).lower())
        finally:
            if outside_file.exists():
                outside_file.unlink()

    def test_absolute_path_blocked(self):
        """Absolute paths must be rejected."""
        with self.assertRaises(ValueError) as ctx:
            read_workspace_file("C:/Windows/system.ini", self.ws_root)
        self.assertIn("absolute", str(ctx.exception).lower())

        with self.assertRaises(ValueError) as ctx2:
            read_workspace_file("/etc/passwd", self.ws_root)
        self.assertIn("absolute", str(ctx2.exception).lower())

    def test_excluded_files_rejected_on_read(self):
        """Attempting to read .env or credential files should be rejected."""
        with self.assertRaises(FileNotFoundError):
            read_workspace_file(".env", self.ws_root)

        with self.assertRaises(FileNotFoundError):
            read_workspace_file("credentials.json", self.ws_root)

    def test_directory_passed_as_file_rejected(self):
        """Passing a directory should raise IsADirectoryError."""
        with self.assertRaises(IsADirectoryError):
            read_workspace_file("subfolder", self.ws_root)

    def test_non_existent_file_rejected(self):
        """Non-existent file should raise FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            read_workspace_file("does_not_exist.txt", self.ws_root)

    def test_binary_file_rejected(self):
        """Binary files containing null bytes or invalid UTF-8 must be rejected."""
        # Extension exclusion
        with self.assertRaises(FileNotFoundError):
            read_workspace_file("binary.bin", self.ws_root)

        # Null byte in text file
        with self.assertRaises(ValueError) as ctx:
            read_workspace_file("corrupt_binary.txt", self.ws_root)
        self.assertIn("binary data", str(ctx.exception).lower())

        # Invalid UTF-8 bytes
        with self.assertRaises(ValueError) as ctx2:
            read_workspace_file("invalid_utf8.txt", self.ws_root)
        self.assertIn("utf-8", str(ctx2.exception).lower())

    def test_endpoint_read_binary_and_invalid_utf8_415(self):
        """Endpoints return 415 Unsupported Media Type for binary or non-UTF-8 files."""
        res1 = self.client.get("/workspace/file", params={"path": "corrupt_binary.txt"})
        self.assertEqual(res1.status_code, 415)
        self.assertIn("binary data", res1.json()["detail"].lower())

        res2 = self.client.get("/workspace/file", params={"path": "invalid_utf8.txt"})
        self.assertEqual(res2.status_code, 415)
        self.assertIn("utf-8", res2.json()["detail"].lower())

    def test_oversized_file_rejected(self):
        """Files larger than 100 KB must be rejected."""
        with self.assertRaises(ValueError) as ctx:
            read_workspace_file("oversized.txt", self.ws_root)
        self.assertIn("exceeds maximum allowed size", str(ctx.exception))

    def test_endpoint_get_workspace_files(self):
        """GET /workspace/files endpoint returns file list and count."""
        response = self.client.get("/workspace/files")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("files", data)
        self.assertIn("count", data)
        self.assertIsInstance(data["files"], list)

    def test_endpoint_get_workspace_file(self):
        """GET /workspace/file?path=... returns file contents."""
        response = self.client.get("/workspace/file", params={"path": "sample.txt"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["path"], "sample.txt")
        self.assertEqual(data["content"], "Hello from PyCraft workspace!")
        self.assertGreater(data["size"], 0)

    def test_endpoint_post_workspace_read(self):
        """POST /workspace/read returns file contents."""
        response = self.client.post("/workspace/read", json={"path": "sample.txt"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["path"], "sample.txt")
        self.assertEqual(data["content"], "Hello from PyCraft workspace!")

    def test_endpoint_read_missing_file_404(self):
        """Reading missing file via endpoint returns 404."""
        response = self.client.get("/workspace/file", params={"path": "missing.txt"})
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["detail"].lower())

    def test_endpoint_read_traversal_400(self):
        """Path traversal attempt returns 400 Bad Request."""
        response = self.client.get("/workspace/file", params={"path": "../outside.txt"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("traversal", response.json()["detail"].lower())

    def test_endpoint_read_directory_400(self):
        """Directory path returns 400 Bad Request."""
        response = self.client.get("/workspace/file", params={"path": "subfolder"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("directory", response.json()["detail"].lower())

    def test_endpoint_read_oversized_413(self):
        """Oversized file returns 413 Request Entity Too Large."""
        response = self.client.get("/workspace/file", params={"path": "oversized.txt"})
        self.assertEqual(response.status_code, 413)
        self.assertIn("exceeds maximum allowed size", response.json()["detail"])

    def test_chat_endpoint_empty_message_rejected(self):
        """Chat endpoint still properly rejects empty message with 400."""
        response = self.client.post("/chat", json={"message": "   "})
        self.assertEqual(response.status_code, 400)
        self.assertIn("cannot be empty", response.json()["detail"].lower())


if __name__ == "__main__":
    unittest.main()
