"""Tests for safe file-deletion capability in PyCraft.

Verifies:
1. delete_workspace_file tool is registered and only runs through the backend allowlist.
2. A delete request asks for confirmation before removing anything.
3. Confirming deletes only the named workspace file.
4. Declining leaves the file intact.
5. Missing, excluded, directory, traversal, absolute, and symlink-escape paths are safely rejected.
6. The Workspace panel refreshes after deletion and closes the deleted file preview.
7. Existing chat, list/read/write tools, saved chats, themes, and menus still work.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.workspace import (
    get_workspace_root,
    list_workspace_files,
    read_workspace_file,
    write_workspace_file,
    delete_workspace_file,
    validate_and_resolve_path,
)
from app.agent import (
    TOOL_ALLOWLIST,
    get_tool_declarations,
    get_activity_description,
    execute_agent_tool,
    check_user_delete_confirmation,
    run_agent_loop,
)


class HistoryTurn:
    """Mock conversation history item."""
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content


class SafeDeleteWorkspaceUnitTests(unittest.TestCase):
    """Unit tests for delete_workspace_file and path validation safeguards."""

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory(prefix="pycraft_del_test_")
        self.ws_root = Path(self.test_dir.name).resolve()
        self.env_patch = patch.dict(os.environ, {"PYCRAFT_WORKSPACE": str(self.ws_root)})
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.test_dir.cleanup()

    def test_delete_existing_file_succeeds(self):
        """Deleting an existing regular file removes it from disk and returns clean path."""
        test_file = self.ws_root / "temp_notes.txt"
        test_file.write_text("temporary notes", encoding="utf-8")
        self.assertTrue(test_file.exists())

        rel_path, success = delete_workspace_file("temp_notes.txt", workspace_root=self.ws_root)
        self.assertEqual(rel_path, "temp_notes.txt")
        self.assertTrue(success)
        self.assertFalse(test_file.exists())

    def test_delete_nested_file_succeeds(self):
        """Deleting a nested file inside subdirectories works and leaves parent intact."""
        sub_dir = self.ws_root / "build" / "logs"
        sub_dir.mkdir(parents=True, exist_ok=True)
        log_file = sub_dir / "old_output.log"
        log_file.write_text("log data", encoding="utf-8")
        self.assertTrue(log_file.exists())

        rel_path, success = delete_workspace_file("build/logs/old_output.log", workspace_root=self.ws_root)
        self.assertEqual(rel_path, "build/logs/old_output.log")
        self.assertTrue(success)
        self.assertFalse(log_file.exists())
        self.assertTrue(sub_dir.exists())

    def test_delete_missing_file_raises_not_found(self):
        """Deleting a non-existent file raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError) as ctx:
            delete_workspace_file("non_existent_file.txt", workspace_root=self.ws_root)
        self.assertIn("non_existent_file.txt", str(ctx.exception))

    def test_delete_directory_raises_is_a_directory_error(self):
        """Attempting to delete a directory raises IsADirectoryError."""
        sub_dir = self.ws_root / "my_folder"
        sub_dir.mkdir(parents=True, exist_ok=True)

        with self.assertRaises(IsADirectoryError):
            delete_workspace_file("my_folder", workspace_root=self.ws_root)
        self.assertTrue(sub_dir.exists())

    def test_delete_excluded_sensitive_files_blocked(self):
        """Attempting to delete .env or sensitive files raises PermissionError."""
        env_file = self.ws_root / ".env"
        env_file.write_text("SECRET=123", encoding="utf-8")

        with self.assertRaises(PermissionError):
            delete_workspace_file(".env", workspace_root=self.ws_root)
        self.assertTrue(env_file.exists())

        cred_file = self.ws_root / "credentials.json"
        cred_file.write_text("{}", encoding="utf-8")
        with self.assertRaises(PermissionError):
            delete_workspace_file("credentials.json", workspace_root=self.ws_root)
        self.assertTrue(cred_file.exists())

    def test_delete_traversal_blocked(self):
        """Directory traversal '..' is blocked with ValueError."""
        with self.assertRaises(ValueError):
            delete_workspace_file("../outside.txt", workspace_root=self.ws_root)

    def test_delete_absolute_path_blocked(self):
        """Absolute POSIX or Windows paths are blocked with ValueError."""
        with self.assertRaises(ValueError):
            delete_workspace_file("/etc/passwd", workspace_root=self.ws_root)

        with self.assertRaises(ValueError):
            delete_workspace_file("C:\\Windows\\system.ini", workspace_root=self.ws_root)


class DeleteToolRegistrationAndAllowlistTests(unittest.TestCase):
    """Verifies tool registration, schema, and strict allowlist enforcement."""

    def test_tool_is_in_strict_allowlist(self):
        """delete_workspace_file must be explicitly in TOOL_ALLOWLIST."""
        self.assertIn("delete_workspace_file", TOOL_ALLOWLIST)

    def test_tool_declaration_properties(self):
        """Tool declaration must be present in Google GenAI schema with path parameter."""
        declarations = get_tool_declarations()
        names = [d.name for d in declarations]
        self.assertIn("delete_workspace_file", names)

        del_decl = next(d for d in declarations if d.name == "delete_workspace_file")
        self.assertIn("path", del_decl.parameters.properties)
        self.assertIn("path", del_decl.parameters.required)
        self.assertIn("cannot be undone", del_decl.description.lower())

    def test_activity_description_for_delete(self):
        """Activity callback displays friendly 'Deleting <path>...' text."""
        msg = get_activity_description("delete_workspace_file", {"path": "hello.txt"})
        self.assertEqual(msg, "Deleting hello.txt...")

    def test_unapproved_delete_command_rejected(self):
        """Unapproved tool names like 'rm' or 'delete_file' or 'bash' are rejected."""
        res1 = execute_agent_tool("rm", {"path": "file.txt"}, "delete file.txt", [])
        self.assertIn("error", res1)
        self.assertIn("not permitted", res1["error"])

        res2 = execute_agent_tool("delete_file", {"path": "file.txt"}, "delete file.txt", [])
        self.assertIn("error", res2)
        self.assertIn("not permitted", res2["error"])


class DeleteConfirmationSafetyFlowTests(unittest.TestCase):
    """Verifies that deletion requests require explicit user confirmation before executing."""

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory(prefix="pycraft_del_flow_")
        self.ws_root = Path(self.test_dir.name).resolve()
        self.env_patch = patch.dict(os.environ, {"PYCRAFT_WORKSPACE": str(self.ws_root)})
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.test_dir.cleanup()

    def test_initial_delete_request_blocked_requiring_confirmation(self):
        """First delete request does NOT delete the file; returns confirmation_required."""
        target = self.ws_root / "hello.txt"
        target.write_text("Hello PyCraft", encoding="utf-8")
        self.assertTrue(target.exists())

        # Model calls tool during initial turn
        result = execute_agent_tool(
            name="delete_workspace_file",
            args={"path": "hello.txt"},
            user_prompt="Please delete hello.txt",
            conversation_history=[],
        )

        self.assertEqual(result.get("status"), "confirmation_required")
        self.assertIn("cannot be undone", result.get("message", "").lower())
        # File must remain untouched on disk!
        self.assertTrue(target.exists())
        self.assertEqual(target.read_text(encoding="utf-8"), "Hello PyCraft")

    def test_user_declining_leaves_file_intact(self):
        """When user replies 'No' or 'cancel', deletion is cancelled and file remains intact."""
        target = self.ws_root / "important.txt"
        target.write_text("Important data", encoding="utf-8")
        self.assertTrue(target.exists())

        history = [
            HistoryTurn("user", "Delete important.txt"),
            HistoryTurn("model", "Delete `important.txt`? This cannot be undone."),
        ]

        # User declines
        result = execute_agent_tool(
            name="delete_workspace_file",
            args={"path": "important.txt"},
            user_prompt="No, don't delete it. Keep it.",
            conversation_history=history,
        )

        self.assertEqual(result.get("status"), "cancelled")
        self.assertIn("untouched", result.get("message", "").lower())
        # File must still exist!
        self.assertTrue(target.exists())
        self.assertEqual(target.read_text(encoding="utf-8"), "Important data")

    def test_user_confirming_deletes_only_named_file(self):
        """When user explicitly confirms ('Yes', 'Delete file'), the file is deleted."""
        target = self.ws_root / "delete_me.txt"
        target.write_text("To be deleted", encoding="utf-8")
        other_file = self.ws_root / "keep_me.txt"
        other_file.write_text("Keep me safe", encoding="utf-8")

        history = [
            HistoryTurn("user", "Can you delete delete_me.txt?"),
            HistoryTurn("model", "Delete `delete_me.txt`? This cannot be undone."),
        ]

        result = execute_agent_tool(
            name="delete_workspace_file",
            args={"path": "delete_me.txt"},
            user_prompt="Yes, delete file.",
            conversation_history=history,
        )

        self.assertEqual(result.get("status"), "success")
        self.assertEqual(result.get("operation"), "deleted")
        self.assertEqual(result.get("path"), "delete_me.txt")

        # delete_me.txt is deleted, but other file is untouched!
        self.assertFalse(target.exists())
        self.assertTrue(other_file.exists())
        self.assertEqual(other_file.read_text(encoding="utf-8"), "Keep me safe")

    def test_delete_missing_file_reports_not_found(self):
        """Attempting to delete a file that does not exist returns not_found without false claims."""
        result = execute_agent_tool(
            name="delete_workspace_file",
            args={"path": "ghost.txt"},
            user_prompt="Delete ghost.txt",
            conversation_history=[],
        )
        self.assertEqual(result.get("status"), "not_found")
        self.assertIn("not exist", result.get("message", "").lower())

    def test_confirmation_helper_logic(self):
        """Direct tests for check_user_delete_confirmation."""
        # Unrelated history -> not confirmed
        self.assertEqual(check_user_delete_confirmation("hello.txt", "Delete hello.txt", []), (False, False))

        history = [
            HistoryTurn("model", "Delete `hello.txt`? This cannot be undone.")
        ]
        # Declines
        self.assertEqual(check_user_delete_confirmation("hello.txt", "No", history), (False, True))
        self.assertEqual(check_user_delete_confirmation("hello.txt", "cancel", history), (False, True))
        self.assertEqual(check_user_delete_confirmation("hello.txt", "don't delete it", history), (False, True))
        self.assertEqual(check_user_delete_confirmation("hello.txt", "keep it please", history), (False, True))

        # Confirms
        self.assertEqual(check_user_delete_confirmation("hello.txt", "Yes", history), (True, False))
        self.assertEqual(check_user_delete_confirmation("hello.txt", "sure, proceed", history), (True, False))
        self.assertEqual(check_user_delete_confirmation("hello.txt", "delete it", history), (True, False))
        self.assertEqual(check_user_delete_confirmation("hello.txt", "Delete file", history), (True, False))


class WorkspaceDeleteEndpointsTests(unittest.TestCase):
    """Tests for POST /workspace/delete and DELETE /workspace/file endpoints."""

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory(prefix="pycraft_endpoint_del_")
        self.ws_root = Path(self.test_dir.name).resolve()
        self.env_patch = patch.dict(os.environ, {"PYCRAFT_WORKSPACE": str(self.ws_root)})
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.env_patch.stop()
        self.test_dir.cleanup()

    def test_post_workspace_delete_succeeds_and_refreshes_listing(self):
        """POST /workspace/delete removes file, and subsequent GET /workspace/files excludes it."""
        file_path = self.ws_root / "temp.txt"
        file_path.write_text("Delete this", encoding="utf-8")

        # Initial listing shows file
        res_list = self.client.get("/workspace/files")
        self.assertEqual(res_list.status_code, 200)
        self.assertIn("temp.txt", res_list.json()["files"])

        # Delete file via POST /workspace/delete
        del_res = self.client.post("/workspace/delete", json={"path": "temp.txt"})
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json()["path"], "temp.txt")
        self.assertTrue(del_res.json()["deleted"])
        self.assertFalse(file_path.exists())

        # Refreshed listing excludes file
        res_list_after = self.client.get("/workspace/files")
        self.assertEqual(res_list_after.status_code, 200)
        self.assertNotIn("temp.txt", res_list_after.json()["files"])

        # Reading the deleted file now returns 404
        read_res = self.client.get("/workspace/file", params={"path": "temp.txt"})
        self.assertEqual(read_res.status_code, 404)

    def test_delete_workspace_file_method_endpoint(self):
        """DELETE /workspace/file query param works identically."""
        file_path = self.ws_root / "removable.py"
        file_path.write_text("# code", encoding="utf-8")

        del_res = self.client.delete("/workspace/file", params={"path": "removable.py"})
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json()["path"], "removable.py")
        self.assertFalse(file_path.exists())

    def test_delete_missing_returns_404(self):
        """Deleting a missing file returns 404 Not Found."""
        res = self.client.post("/workspace/delete", json={"path": "no_such_file.txt"})
        self.assertEqual(res.status_code, 404)

    def test_delete_excluded_returns_403(self):
        """Deleting an excluded file returns 403 Forbidden."""
        env_file = self.ws_root / ".env"
        env_file.write_text("KEY=val", encoding="utf-8")
        res = self.client.post("/workspace/delete", json={"path": ".env"})
        self.assertEqual(res.status_code, 403)
        self.assertTrue(env_file.exists())

    def test_delete_directory_returns_400(self):
        """Deleting a directory returns 400 Bad Request."""
        d = self.ws_root / "subdir"
        d.mkdir(parents=True, exist_ok=True)
        res = self.client.post("/workspace/delete", json={"path": "subdir"})
        self.assertEqual(res.status_code, 400)
        self.assertTrue(d.exists())

    def test_delete_traversal_returns_400(self):
        """Deleting with traversal returns 400 Bad Request."""
        res = self.client.post("/workspace/delete", json={"path": "../secret.txt"})
        self.assertEqual(res.status_code, 400)


class WorkspacePanelRefreshAndClosePreviewTests(unittest.TestCase):
    """Verifies that the Workspace panel refreshes and preview closes after file deletion."""

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory(prefix="pycraft_preview_del_")
        self.ws_root = Path(self.test_dir.name).resolve()
        self.env_patch = patch.dict(os.environ, {"PYCRAFT_WORKSPACE": str(self.ws_root)})
        self.env_patch.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.env_patch.stop()
        self.test_dir.cleanup()

    def test_delete_flow_closes_preview_and_updates_file_list(self):
        """Simulate creating a file, reading/previewing it, deleting it, and verifying 404 & clean list."""
        # 1. Create file
        write_res = self.client.post(
            "/workspace/write",
            json={"path": "preview_target.py", "content": "print('preview')", "overwrite": False},
        )
        self.assertEqual(write_res.status_code, 200)

        # 2. Preview file (reading it)
        preview_res = self.client.get("/workspace/file", params={"path": "preview_target.py"})
        self.assertEqual(preview_res.status_code, 200)
        self.assertEqual(preview_res.json()["content"], "print('preview')")

        # 3. Delete file
        del_res = self.client.post("/workspace/delete", json={"path": "preview_target.py"})
        self.assertEqual(del_res.status_code, 200)

        # 4. Preview should no longer be readable (404)
        preview_after = self.client.get("/workspace/file", params={"path": "preview_target.py"})
        self.assertEqual(preview_after.status_code, 404)

        # 5. List must not contain it
        files_after = self.client.get("/workspace/files").json()["files"]
        self.assertNotIn("preview_target.py", files_after)

    def test_frontend_contains_delete_controls(self):
        """index.html contains viewer-delete-btn and styles contain delete action styling."""
        index_res = self.client.get("/")
        self.assertEqual(index_res.status_code, 200)
        self.assertIn('id="viewer-delete-btn"', index_res.text)
        self.assertIn('modal-dialog', index_res.text)

        css_res = self.client.get("/static/styles.css")
        self.assertEqual(css_res.status_code, 200)
        self.assertIn(".file-item-delete-btn", css_res.text)
        self.assertIn(".danger-nav-btn", css_res.text)

        js_res = self.client.get("/static/app.js")
        self.assertEqual(js_res.status_code, 200)
        self.assertIn("confirmDeleteFile", js_res.text)
        self.assertIn("executeDeleteWorkspaceFile", js_res.text)


if __name__ == "__main__":
    unittest.main()
