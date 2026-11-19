"""Tests for PyCraft Phase 3 and Phase 4 workspace tools and endpoints."""

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
    write_workspace_file,
    validate_and_resolve_path,
)


class WorkspaceToolTests(unittest.TestCase):
    """Test suite for workspace listing, reading, and writing safeguards."""

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

    # -----------------------------------------------------------------------
    # Phase 3: Listing & Reading Tests
    # -----------------------------------------------------------------------

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

    def test_read_path_traversal_blocked(self):
        """Directory traversal attempts with .. must be rejected."""
        with self.assertRaises(ValueError) as ctx:
            read_workspace_file("../outside.txt", self.ws_root)
        self.assertIn("traversal", str(ctx.exception).lower())

        with self.assertRaises(ValueError) as ctx2:
            read_workspace_file("subfolder/../../outside.txt", self.ws_root)
        self.assertIn("traversal", str(ctx2.exception).lower())

    def test_read_symlink_escape_blocked(self):
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

    def test_read_absolute_path_blocked(self):
        """Absolute paths must be rejected."""
        with self.assertRaises(ValueError) as ctx:
            read_workspace_file("C:/Windows/system.ini", self.ws_root)
        self.assertIn("absolute", str(ctx.exception).lower())

        with self.assertRaises(ValueError) as ctx2:
            read_workspace_file("/etc/passwd", self.ws_root)
        self.assertIn("absolute", str(ctx2.exception).lower())

    def test_read_excluded_files_rejected(self):
        """Attempting to read .env or credential files should be rejected with FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            read_workspace_file(".env", self.ws_root)

        with self.assertRaises(FileNotFoundError):
            read_workspace_file("credentials.json", self.ws_root)

    def test_read_directory_passed_as_file_rejected(self):
        """Passing a directory to read should raise IsADirectoryError."""
        with self.assertRaises(IsADirectoryError):
            read_workspace_file("subfolder", self.ws_root)

    def test_read_non_existent_file_rejected(self):
        """Non-existent file should raise FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            read_workspace_file("does_not_exist.txt", self.ws_root)

    def test_read_binary_file_rejected(self):
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

    def test_read_oversized_file_rejected(self):
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

    def test_endpoint_read_binary_and_invalid_utf8_415(self):
        """Endpoints return 415 Unsupported Media Type for binary or non-UTF-8 files."""
        res1 = self.client.get("/workspace/file", params={"path": "corrupt_binary.txt"})
        self.assertEqual(res1.status_code, 415)
        self.assertIn("binary data", res1.json()["detail"].lower())

        res2 = self.client.get("/workspace/file", params={"path": "invalid_utf8.txt"})
        self.assertEqual(res2.status_code, 415)
        self.assertIn("utf-8", res2.json()["detail"].lower())

    def test_endpoint_read_directory_400(self):
        """Directory path returns 400 Bad Request."""
        response = self.client.get("/workspace/file", params={"path": "subfolder"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("directory", response.json()["detail"].lower())

    def test_endpoint_read_missing_file_404(self):
        """Reading missing file via endpoint returns 404."""
        response = self.client.get("/workspace/file", params={"path": "missing.txt"})
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["detail"].lower())

    def test_endpoint_read_oversized_413(self):
        """Oversized file returns 413 Content Too Large."""
        response = self.client.get("/workspace/file", params={"path": "oversized.txt"})
        self.assertEqual(response.status_code, 413)
        self.assertIn("exceeds maximum allowed size", response.json()["detail"])

    def test_endpoint_read_traversal_400(self):
        """Path traversal attempt returns 400 Bad Request."""
        response = self.client.get("/workspace/file", params={"path": "../outside.txt"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("traversal", response.json()["detail"].lower())

    # -----------------------------------------------------------------------
    # Phase 4: Writing Tests (Create, Update, Safeguards)
    # -----------------------------------------------------------------------

    def test_write_new_file_succeeds_and_lists_and_reads(self):
        """Creating a new text file succeeds, writes atomically, and is listable and readable."""
        content = "Phase 4 written content: Hello World!"
        path, operation, bytes_written = write_workspace_file(
            "new_note.txt", content, overwrite=False, workspace_root=self.ws_root
        )
        self.assertEqual(path, "new_note.txt")
        self.assertEqual(operation, "created")
        self.assertEqual(bytes_written, len(content.encode("utf-8")))

        # Verify listed
        files = list_workspace_files(self.ws_root)
        self.assertIn("new_note.txt", files)

        # Verify readable
        read_path, read_content, size = read_workspace_file("new_note.txt", self.ws_root)
        self.assertEqual(read_path, "new_note.txt")
        self.assertEqual(read_content, content)
        self.assertEqual(size, bytes_written)

    def test_write_nested_new_file_creates_parent_directories(self):
        """Writing to a nested path automatically creates parent directories within the workspace."""
        content = "Nested file created cleanly"
        path, operation, bytes_written = write_workspace_file(
            "docs/sub/notes.txt", content, overwrite=False, workspace_root=self.ws_root
        )
        self.assertEqual(path, "docs/sub/notes.txt")
        self.assertEqual(operation, "created")

        read_path, read_content, _ = read_workspace_file("docs/sub/notes.txt", self.ws_root)
        self.assertEqual(read_content, content)

    def test_write_existing_file_without_overwrite_raises_conflict(self):
        """Writing to an existing file when overwrite=False raises FileExistsError (and 409)."""
        original_content = (self.ws_root / "sample.txt").read_text(encoding="utf-8")

        # 1. Direct function call
        with self.assertRaises(FileExistsError) as ctx:
            write_workspace_file("sample.txt", "New text", overwrite=False, workspace_root=self.ws_root)
        self.assertIn("already exists", str(ctx.exception))

        # 2. Endpoint call
        response = self.client.post(
            "/workspace/write",
            json={"path": "sample.txt", "content": "New text", "overwrite": False},
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("already exists", response.json()["detail"])

        # Content must be preserved unchanged
        self.assertEqual((self.ws_root / "sample.txt").read_text(encoding="utf-8"), original_content)

    def test_write_existing_file_with_overwrite_updates_content(self):
        """Writing to an existing file with overwrite=True successfully updates content."""
        new_content = "Completely updated content for sample.txt"

        # Endpoint call
        response = self.client.post(
            "/workspace/write",
            json={"path": "sample.txt", "content": new_content, "overwrite": True},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["path"], "sample.txt")
        self.assertEqual(data["operation"], "updated")
        self.assertEqual(data["bytes_written"], len(new_content.encode("utf-8")))

        # Verify content on disk
        _, read_content, _ = read_workspace_file("sample.txt", self.ws_root)
        self.assertEqual(read_content, new_content)

    def test_write_traversal_blocked(self):
        """Writing with path traversal ('..') is strictly rejected with 400."""
        with self.assertRaises(ValueError) as ctx:
            write_workspace_file("../hacked.txt", "payload", overwrite=True, workspace_root=self.ws_root)
        self.assertIn("traversal", str(ctx.exception).lower())

        response = self.client.post(
            "/workspace/write",
            json={"path": "subfolder/../../outside.txt", "content": "payload", "overwrite": True},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("traversal", response.json()["detail"].lower())

    def test_write_symlink_escape_blocked(self):
        """Writing through a symlink pointing outside the workspace must be rejected."""
        outside_file = self.ws_root.parent / "secret_write_outside.txt"
        outside_file.write_text("INITIAL", encoding="utf-8")
        try:
            symlink_path = self.ws_root / "escape_write_link.txt"
            try:
                symlink_path.symlink_to(outside_file)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks not supported without admin privileges on Windows.")

            with self.assertRaises(PermissionError) as ctx:
                write_workspace_file("escape_write_link.txt", "MALICIOUS", overwrite=True, workspace_root=self.ws_root)
            self.assertIn("workspace boundary", str(ctx.exception).lower())
        finally:
            if outside_file.exists():
                outside_file.unlink()

    def test_write_absolute_path_blocked(self):
        """Writing with absolute path is rejected with 400."""
        with self.assertRaises(ValueError) as ctx:
            write_workspace_file("C:/Windows/System32/hacked.txt", "bad", overwrite=True, workspace_root=self.ws_root)
        self.assertIn("absolute", str(ctx.exception).lower())

        response = self.client.post(
            "/workspace/write",
            json={"path": "/etc/passwd", "content": "root", "overwrite": True},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("absolute", response.json()["detail"].lower())

    def test_write_excluded_sensitive_files_blocked(self):
        """Writing to .env, credentials, or sensitive files is rejected with PermissionError (403)."""
        # .env
        with self.assertRaises(PermissionError):
            write_workspace_file(".env", "LEAK=true", overwrite=True, workspace_root=self.ws_root)

        res_env = self.client.post(
            "/workspace/write",
            json={"path": ".env", "content": "LEAK=true", "overwrite": True},
        )
        self.assertEqual(res_env.status_code, 403)
        self.assertIn("excluded or sensitive", res_env.json()["detail"].lower())

        # credentials.json
        res_cred = self.client.post(
            "/workspace/write",
            json={"path": "credentials.json", "content": "{}", "overwrite": True},
        )
        self.assertEqual(res_cred.status_code, 403)

        # token.txt
        res_tok = self.client.post(
            "/workspace/write",
            json={"path": "app_token.txt", "content": "xyz", "overwrite": True},
        )
        self.assertEqual(res_tok.status_code, 403)

        # secret.key
        res_key = self.client.post(
            "/workspace/write",
            json={"path": "private.key", "content": "key", "overwrite": True},
        )
        self.assertEqual(res_key.status_code, 403)

    def test_write_to_existing_directory_rejected(self):
        """Attempting to write to an existing directory path raises IsADirectoryError (400)."""
        with self.assertRaises(IsADirectoryError):
            write_workspace_file("subfolder", "data", overwrite=True, workspace_root=self.ws_root)

        response = self.client.post(
            "/workspace/write",
            json={"path": "subfolder", "content": "data", "overwrite": True},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("directory", response.json()["detail"].lower())

    def test_write_oversized_content_rejected(self):
        """Writing content larger than 100 KB is rejected with 413 Content Too Large."""
        big_content = "X" * (MAX_FILE_SIZE_BYTES + 2048)
        with self.assertRaises(ValueError) as ctx:
            write_workspace_file("big.txt", big_content, overwrite=True, workspace_root=self.ws_root)
        self.assertIn("exceeds maximum allowed file size", str(ctx.exception))

        response = self.client.post(
            "/workspace/write",
            json={"path": "big.txt", "content": big_content, "overwrite": True},
        )
        self.assertEqual(response.status_code, 413)
        self.assertIn("exceeds maximum allowed file size", response.json()["detail"])

    def test_write_null_byte_binary_rejected(self):
        """Writing content containing binary null bytes is rejected with 415."""
        binary_content = "hello\x00world"
        with self.assertRaises(ValueError) as ctx:
            write_workspace_file("null.txt", binary_content, overwrite=True, workspace_root=self.ws_root)
        self.assertIn("null byte", str(ctx.exception).lower())

        response = self.client.post(
            "/workspace/write",
            json={"path": "null.txt", "content": binary_content, "overwrite": True},
        )
        self.assertEqual(response.status_code, 415)
        self.assertIn("null byte", response.json()["detail"].lower())

    def test_write_empty_path_rejected(self):
        """Writing with an empty or whitespace path is rejected with 400."""
        with self.assertRaises(ValueError) as ctx:
            write_workspace_file("   ", "data", overwrite=True, workspace_root=self.ws_root)
        self.assertIn("cannot be empty", str(ctx.exception).lower())

        response = self.client.post(
            "/workspace/write",
            json={"path": "   ", "content": "data", "overwrite": True},
        )
        self.assertEqual(response.status_code, 400)

    # -----------------------------------------------------------------------
    # Workspace Panel UI & Flow Tests
    # -----------------------------------------------------------------------

    def test_index_page_contains_workspace_panel_elements(self):
        """Index HTML must include the workspace toggle button, panel, and preview viewer."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("workspace-toggle-btn", html)
        self.assertIn("workspace-panel", html)
        self.assertIn("workspace-file-list", html)
        self.assertIn("workspace-viewer", html)
        self.assertIn("viewer-code", html)
        # Ensure clean branding (no phase labels, provider badges, or assistant labels)
        self.assertNotIn("Phase 1", html)
        self.assertNotIn("Phase 2", html)
        self.assertNotIn("Phase 3", html)
        self.assertNotIn("Phase 4", html)
        self.assertNotIn("powered by", html.lower())

    def test_workspace_panel_flow_list_read_write_refresh(self):
        """Panel flow: lists files, reads selected file, and reflects newly written file on refresh."""
        # 1. List files (initial state)
        list_res = self.client.get("/workspace/files")
        self.assertEqual(list_res.status_code, 200)
        initial_files = list_res.json()["files"]
        self.assertIn("sample.txt", initial_files)

        # 2. Select and read a file (displays content and relative path)
        read_res = self.client.get("/workspace/file", params={"path": "sample.txt"})
        self.assertEqual(read_res.status_code, 200)
        read_data = read_res.json()
        self.assertEqual(read_data["path"], "sample.txt")
        self.assertEqual(read_data["content"], "Hello from PyCraft workspace!")

        # 3. Simulate an agent write operation
        write_res = self.client.post(
            "/workspace/write",
            json={"path": "agent_code.py", "content": "print('hello from PyCraft agent')", "overwrite": False},
        )
        self.assertEqual(write_res.status_code, 200)
        self.assertEqual(write_res.json()["operation"], "created")

        # 4. Refresh file list (new file must appear in panel data)
        refreshed_list_res = self.client.get("/workspace/files")
        self.assertEqual(refreshed_list_res.status_code, 200)
        updated_files = refreshed_list_res.json()["files"]
        self.assertIn("agent_code.py", updated_files)
        self.assertIn("sample.txt", updated_files)

        # 5. Read newly created file
        new_file_res = self.client.get("/workspace/file", params={"path": "agent_code.py"})
        self.assertEqual(new_file_res.status_code, 200)
        self.assertEqual(new_file_res.json()["content"], "print('hello from PyCraft agent')")

    # -----------------------------------------------------------------------
    # Chat Preservation Test
    # -----------------------------------------------------------------------

    def test_chat_endpoint_empty_message_rejected(self):
        """Chat endpoint still properly rejects empty message with 400."""
        response = self.client.post("/chat", json={"message": "   "})
        self.assertEqual(response.status_code, 400)
        self.assertIn("cannot be empty", response.json()["detail"].lower())


if __name__ == "__main__":
    unittest.main()
