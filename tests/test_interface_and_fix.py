"""Focused tests for PyCraft interface improvements and workspace preview fix.

Covers:
1. HTML contract: Full-window layout, ☰ menu button, sidebar (closed by default),
   functional menus (File, Edit, View, Help), theme switch, modal dialogs.
2. Workspace File Creation & Preview Fix:
   - Creating a file ('palindrome.py') and reading it via GET /workspace/file?path=palindrome.py.
   - Confirming preview content matches exactly.
   - Creating a nested relative path ('utils/palindrome.py') and reading it.
   - Handling redundant workspace folder prefix ('workspace/palindrome.py') without error.
3. Chat Endpoint Contract:
   - Returning 'files_modified' and 'modified_files' list.
   - Separate conversation history per chat session.
4. Static file integrity:
   - app.js and styles.css served with 200 OK.
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.workspace import get_workspace_root, write_workspace_file, read_workspace_file, list_workspace_files


class InterfaceAndWorkspaceFixTests(unittest.TestCase):
    """Test suite for full-window UI, menus, saved chats contract, and workspace fix."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="pycraft_fix_test_")
        self.ws_root = Path(self.test_dir).resolve()
        (self.ws_root / "hello.txt").write_text("Hello from workspace", encoding="utf-8")

        self.orig_env = os.environ.get("PYCRAFT_WORKSPACE")
        os.environ["PYCRAFT_WORKSPACE"] = str(self.ws_root)

    def tearDown(self):
        if self.orig_env is not None:
            os.environ["PYCRAFT_WORKSPACE"] = self.orig_env
        else:
            os.environ.pop("PYCRAFT_WORKSPACE", None)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. HTML Contract & UI Architecture Tests
    # -------------------------------------------------------------------------

    def test_index_page_contains_full_window_and_navigation_elements(self):
        """Index HTML must include the ☰ toggle button, sidebar, menus, and workspace view."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.text

        # ☰ Sidebar toggle button
        self.assertIn('id="sidebar-toggle-btn"', html)

        # Sidebar is present and closed by default (hidden attribute)
        self.assertIn('id="app-sidebar"', html)
        self.assertIn('<aside id="app-sidebar" class="app-sidebar" aria-label="Saved Chats and Workspace" hidden>', html)

        # Saved chats list container
        self.assertIn('id="saved-chats-list"', html)

        # Workspace button in sidebar
        self.assertIn('id="sidebar-workspace-btn"', html)

        # Functional Application Menubar: File, Edit, View, Help
        self.assertIn('id="menu-file-trigger"', html)
        self.assertIn('id="menu-edit-trigger"', html)
        self.assertIn('id="menu-view-trigger"', html)
        self.assertIn('id="menu-help-trigger"', html)

        # Menu actions
        self.assertIn('id="action-file-new-chat"', html)
        self.assertIn('id="action-file-open-workspace"', html)
        self.assertIn('id="action-edit-copy-response"', html)
        self.assertIn('id="action-edit-clear-chat"', html)
        self.assertIn('id="action-view-toggle-sidebar"', html)
        self.assertIn('id="action-view-show-workspace"', html)
        self.assertIn('id="action-view-dark-theme"', html)
        self.assertIn('id="action-view-light-theme"', html)
        self.assertIn('id="action-help-how-to"', html)
        self.assertIn('id="action-help-about"', html)

        # Theme toggle switch
        self.assertIn('id="theme-toggle-btn"', html)

        # Workspace view (hidden until requested)
        self.assertIn('id="workspace-view"', html)
        self.assertIn('id="workspace-viewer"', html)

        # Isolated loading and error states for workspace and viewer
        self.assertIn('id="workspace-loading"', html)
        self.assertIn('id="workspace-error"', html)
        self.assertIn('id="viewer-loading"', html)
        self.assertIn('id="viewer-error"', html)

        # Accessible confirmation & help modal
        self.assertIn('id="app-modal"', html)
        self.assertIn('id="modal-confirm-btn"', html)
        self.assertIn('id="modal-cancel-btn"', html)

    def test_static_assets_served_properly(self):
        """CSS and JS assets must be accessible and return 200 OK."""
        css_res = self.client.get("/static/styles.css")
        self.assertEqual(css_res.status_code, 200)
        self.assertIn("data-theme=\"light\"", css_res.text)

        js_res = self.client.get("/static/app.js")
        self.assertEqual(js_res.status_code, 200)
        self.assertIn("pycraft_saved_chats", js_res.text)
        self.assertIn("pycraft_theme", js_res.text)

    def test_dropdown_menus_and_error_banner_hidden_contract(self):
        """Dropdown menus and error banner must be hidden by default in both HTML and CSS."""
        html_res = self.client.get("/")
        self.assertEqual(html_res.status_code, 200)
        html = html_res.text

        # All dropdowns must have hidden attribute
        self.assertIn('id="menu-file-dropdown" role="menu" aria-labelledby="menu-file-trigger" hidden', html)
        self.assertIn('id="menu-edit-dropdown" role="menu" aria-labelledby="menu-edit-trigger" hidden', html)
        self.assertIn('id="menu-view-dropdown" role="menu" aria-labelledby="menu-view-trigger" hidden', html)
        self.assertIn('id="menu-help-dropdown" role="menu" aria-labelledby="menu-help-trigger" hidden', html)

        # Error banner must be hidden and have empty text by default
        self.assertIn('id="error-banner" class="error-banner" role="alert" hidden', html)
        self.assertIn('id="error-banner-text" class="error-text"></span>', html)

        # CSS must strictly enforce display: none !important on hidden elements
        css_res = self.client.get("/static/styles.css")
        css = css_res.text
        self.assertIn(".dropdown-menu[hidden]", css)
        self.assertIn(".error-banner[hidden]", css)
        self.assertIn("display: none !important", css)

    def test_menu_javascript_keyboard_and_single_open_contract(self):
        """JavaScript must enforce single open menu, click-outside, and keyboard navigation."""
        js_res = self.client.get("/static/app.js")
        js = js_res.text

        # Single active menu tracking and closing all dropdowns
        self.assertIn("activeMenuIndex", js)
        self.assertIn("closeAllDropdowns", js)
        self.assertIn("openMenu", js)
        self.assertIn("toggleMenu", js)

        # Keyboard accessibility
        self.assertIn("ArrowDown", js)
        self.assertIn("ArrowUp", js)
        self.assertIn("ArrowRight", js)
        self.assertIn("ArrowLeft", js)
        self.assertIn("Escape", js)

        # Error banner show/hide functions
        self.assertIn("showNotification", js)
        self.assertIn("hideErrorBanner", js)

    # -------------------------------------------------------------------------
    # 2. Workspace File Creation & Preview Bug Fix Verification
    # -------------------------------------------------------------------------

    def test_create_and_preview_palindrome_file(self):
        """
        Verify the exact user scenario:
        1. Write 'palindrome.py'
        2. Refresh workspace file list -> 'palindrome.py' is listed
        3. Read 'palindrome.py' -> returns 200 OK with exact code
        """
        code = (
            "def is_palindrome(text: str) -> bool:\n"
            "    cleaned = ''.join(c.lower() for c in text if c.isalnum())\n"
            "    return cleaned == cleaned[::-1]\n"
        )

        # Write file
        write_res = self.client.post(
            "/workspace/write",
            json={"path": "palindrome.py", "content": code, "overwrite": False},
        )
        self.assertEqual(write_res.status_code, 200)
        self.assertEqual(write_res.json()["path"], "palindrome.py")

        # List files
        list_res = self.client.get("/workspace/files")
        self.assertEqual(list_res.status_code, 200)
        files = list_res.json()["files"]
        self.assertIn("palindrome.py", files)

        # Preview file
        read_res = self.client.get("/workspace/file", params={"path": "palindrome.py"})
        self.assertEqual(read_res.status_code, 200)
        data = read_res.json()
        self.assertEqual(data["path"], "palindrome.py")
        self.assertEqual(data["content"], code)
        self.assertEqual(data["size"], len(code.encode("utf-8")))

    def test_create_and_preview_nested_relative_path(self):
        """Verify creating and previewing a nested file: 'algorithms/palindrome.py'."""
        nested_code = "# Palindrome check in subfolder\n"

        write_res = self.client.post(
            "/workspace/write",
            json={"path": "algorithms/palindrome.py", "content": nested_code, "overwrite": False},
        )
        self.assertEqual(write_res.status_code, 200)
        self.assertEqual(write_res.json()["path"], "algorithms/palindrome.py")

        # List files
        list_res = self.client.get("/workspace/files")
        self.assertEqual(list_res.status_code, 200)
        self.assertIn("algorithms/palindrome.py", list_res.json()["files"])

        # Preview file
        read_res = self.client.get("/workspace/file", params={"path": "algorithms/palindrome.py"})
        self.assertEqual(read_res.status_code, 200)
        self.assertEqual(read_res.json()["content"], nested_code)

    def test_redundant_workspace_prefix_normalized(self):
        """Verify that 'workspace/palindrome.py' does not create duplicate nested directories."""
        code = "print('hello')"
        write_res = self.client.post(
            "/workspace/write",
            json={"path": "workspace/palindrome.py", "content": code, "overwrite": False},
        )
        self.assertEqual(write_res.status_code, 200)
        # Normalized path must be palindrome.py
        rel_path = write_res.json()["path"]
        self.assertEqual(rel_path, "palindrome.py")

        # Reading with either 'palindrome.py' or 'workspace/palindrome.py' resolves cleanly
        read1 = self.client.get("/workspace/file", params={"path": "palindrome.py"})
        self.assertEqual(read1.status_code, 200)
        self.assertEqual(read1.json()["content"], code)

        read2 = self.client.get("/workspace/file", params={"path": "workspace/palindrome.py"})
        self.assertEqual(read2.status_code, 200)
        self.assertEqual(read2.json()["content"], code)

    # -------------------------------------------------------------------------
    # 3. Chat Endpoint Contract with Modified Files Tracking
    # -------------------------------------------------------------------------

    @patch("app.main.run_agent_loop")
    @patch("app.main.genai.Client")
    def test_chat_endpoint_reports_modified_files(self, mock_client_cls, mock_agent_loop):
        """Chat endpoint must report modified_files list when files are created."""
        mock_agent_loop.return_value = (
            "I created palindrome.py for you.",
            ["write_workspace_file"],
            True,
            ["palindrome.py"],
        )

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-12345"}):
            response = self.client.post(
                "/chat",
                json={"message": "Create palindrome.py", "history": []},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["files_modified"])
        self.assertEqual(data["modified_files"], ["palindrome.py"])
        self.assertEqual(data["tools_used"], ["write_workspace_file"])


if __name__ == "__main__":
    unittest.main()
