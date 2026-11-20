"""Tests for PyCraft Phase 5: Autonomous Agent Loop and Workspace File Tools.

Covers:
- Tool declarations and schemas
- Activity description generation
- Strict allowlist enforcement (blocking shell, arbitrary commands, unknown tools)
- Overwrite safety and user confirmation checking
- Workspace tool execution through execute_agent_tool
- Agent loop execution, multi-turn tool handling, and max iteration limit
- FastAPI /chat endpoint integration (JSON and SSE streaming)
"""

import asyncio
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from google.genai import types

from app.agent import (
    MAX_TOOL_ITERATIONS,
    TOOL_ALLOWLIST,
    check_user_overwrite_confirmation,
    execute_agent_tool,
    get_activity_description,
    get_tool_declarations,
    run_agent_loop,
)
from app.main import app
from app.workspace import get_workspace_root


class AgentToolDeclarationTests(unittest.TestCase):
    """Test tool declarations and schemas passed to Gemini."""

    def test_tool_declarations_content_and_names(self):
        decls = get_tool_declarations()
        self.assertEqual(len(decls), 3)
        names = {d.name for d in decls}
        self.assertEqual(names, {"list_workspace_files", "read_workspace_file", "write_workspace_file"})

    def test_tool_declarations_parameters(self):
        decls = {d.name: d for d in get_tool_declarations()}

        # list_workspace_files takes no required parameters
        list_decl = decls["list_workspace_files"]
        self.assertIsNotNone(list_decl.description)

        # read_workspace_file requires path
        read_decl = decls["read_workspace_file"]
        self.assertIn("path", read_decl.parameters.properties)
        self.assertIn("path", read_decl.parameters.required)

        # write_workspace_file requires path and content
        write_decl = decls["write_workspace_file"]
        self.assertIn("path", write_decl.parameters.properties)
        self.assertIn("content", write_decl.parameters.properties)
        self.assertIn("overwrite", write_decl.parameters.properties)
        self.assertIn("path", write_decl.parameters.required)
        self.assertIn("content", write_decl.parameters.required)


class AgentActivityDescriptionTests(unittest.TestCase):
    """Test user-friendly activity strings generated during tool execution."""

    def test_activity_descriptions(self):
        self.assertEqual(
            get_activity_description("list_workspace_files", {}),
            "Listing workspace files...",
        )
        self.assertEqual(
            get_activity_description("read_workspace_file", {"path": "main.py"}),
            "Reading main.py...",
        )
        self.assertEqual(
            get_activity_description("read_workspace_file", {}),
            "Reading workspace file...",
        )
        self.assertEqual(
            get_activity_description("write_workspace_file", {"path": "notes.txt"}),
            "Writing notes.txt...",
        )
        self.assertEqual(
            get_activity_description("write_workspace_file", {}),
            "Writing workspace file...",
        )
        self.assertEqual(
            get_activity_description("unknown_tool", {}),
            "Running unknown_tool...",
        )


class OverwriteConfirmationSafetyTests(unittest.TestCase):
    """Test the overwrite confirmation checker preventing accidental file replacement."""

    def test_direct_overwrite_keywords_in_prompt(self):
        # Current user prompt explicitly instructs an overwrite/replace/update
        self.assertTrue(check_user_overwrite_confirmation("test.py", "Please overwrite test.py with new code", []))
        self.assertTrue(check_user_overwrite_confirmation("notes.txt", "replace notes.txt with hello", []))
        self.assertTrue(check_user_overwrite_confirmation("main.py", "update main.py", []))
        self.assertTrue(check_user_overwrite_confirmation("script.py", "rewrite script.py completely", []))

    def test_no_confirmation_in_prompt(self):
        # Ordinary prompts without overwrite instructions
        self.assertFalse(check_user_overwrite_confirmation("hello.txt", "Create a file named hello.txt", []))
        self.assertFalse(check_user_overwrite_confirmation("hello.txt", "What is inside hello.txt?", []))

    def test_affirmative_follow_up_after_assistant_warning(self):
        # Previous assistant turn warned that the file exists, user says yes
        class HistoryTurn:
            def __init__(self, role, content):
                self.role = role
                self.content = content

        history = [
            HistoryTurn("user", "Save this text to hello.txt"),
            HistoryTurn("model", "The file 'hello.txt' already exists in the workspace. Would you like to overwrite it?"),
        ]

        self.assertTrue(check_user_overwrite_confirmation("hello.txt", "Yes, go ahead.", history))
        self.assertTrue(check_user_overwrite_confirmation("hello.txt", "sure, proceed", history))
        self.assertTrue(check_user_overwrite_confirmation("hello.txt", "okay, overwrite it", history))
        self.assertTrue(check_user_overwrite_confirmation("hello.txt", "yes please", history))

        # User says no or changes subject
        self.assertFalse(check_user_overwrite_confirmation("hello.txt", "No, keep it.", history))
        self.assertFalse(check_user_overwrite_confirmation("hello.txt", "What else is there?", history))


class AgentToolExecutionTests(unittest.TestCase):
    """Test execution of allowed and rejected tools through execute_agent_tool."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="pycraft_test_agent_")
        self.ws_root = Path(self.test_dir).resolve()
        (self.ws_root / "existing.txt").write_text("Original content", encoding="utf-8")

        self.orig_env = os.environ.get("PYCRAFT_WORKSPACE")
        os.environ["PYCRAFT_WORKSPACE"] = str(self.ws_root)

    def tearDown(self):
        if self.orig_env is not None:
            os.environ["PYCRAFT_WORKSPACE"] = self.orig_env
        else:
            os.environ.pop("PYCRAFT_WORKSPACE", None)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_unapproved_tool_rejected(self):
        # Shell commands or unknown tool names must be rejected
        res = execute_agent_tool("execute_bash", {"command": "ls"}, "run bash", [])
        self.assertIn("error", res)
        self.assertIn("not permitted", res["error"])

        res2 = execute_agent_tool("delete_file", {"path": "existing.txt"}, "delete", [])
        self.assertIn("error", res2)
        self.assertIn("not permitted", res2["error"])

    def test_list_workspace_files_tool(self):
        res = execute_agent_tool("list_workspace_files", {}, "list files", [])
        self.assertIn("files", res)
        self.assertIn("count", res)
        self.assertEqual(res["files"], ["existing.txt"])
        self.assertEqual(res["count"], 1)

    def test_read_workspace_file_tool(self):
        # Success
        res = execute_agent_tool("read_workspace_file", {"path": "existing.txt"}, "read file", [])
        self.assertEqual(res.get("path"), "existing.txt")
        self.assertEqual(res.get("content"), "Original content")

        # Missing path argument
        res_err = execute_agent_tool("read_workspace_file", {}, "read file", [])
        self.assertIn("error", res_err)

        # Non-existent file
        res_missing = execute_agent_tool("read_workspace_file", {"path": "nope.txt"}, "read file", [])
        self.assertIn("error", res_missing)

    def test_write_new_workspace_file_tool(self):
        res = execute_agent_tool(
            "write_workspace_file",
            {"path": "new_file.txt", "content": "Brand new file!"},
            "create new_file.txt",
            [],
        )
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("operation"), "created")
        self.assertEqual(res.get("path"), "new_file.txt")
        self.assertTrue((self.ws_root / "new_file.txt").exists())
        self.assertEqual((self.ws_root / "new_file.txt").read_text(encoding="utf-8"), "Brand new file!")

    def test_write_existing_file_without_confirmation_blocked(self):
        res = execute_agent_tool(
            "write_workspace_file",
            {"path": "existing.txt", "content": "Replaced content", "overwrite": True},
            "Save something to existing.txt",
            [],
        )
        # Must be blocked as conflict despite overwrite=True from model
        self.assertEqual(res.get("status"), "conflict")
        self.assertIn("already exists", res.get("message", ""))
        # Original content must remain untouched
        self.assertEqual((self.ws_root / "existing.txt").read_text(encoding="utf-8"), "Original content")

    def test_write_existing_file_with_user_confirmation_succeeds(self):
        res = execute_agent_tool(
            "write_workspace_file",
            {"path": "existing.txt", "content": "Updated content", "overwrite": True},
            "Please overwrite existing.txt with new code",
            [],
        )
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("operation"), "updated")
        self.assertEqual((self.ws_root / "existing.txt").read_text(encoding="utf-8"), "Updated content")


class AgentLoopExecutionTests(unittest.IsolatedAsyncioTestCase):
    """Test the multi-turn agent loop with mocked Gemini responses."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="pycraft_test_loop_")
        self.ws_root = Path(self.test_dir).resolve()
        (self.ws_root / "hello.txt").write_text("Hello World!", encoding="utf-8")

        self.orig_env = os.environ.get("PYCRAFT_WORKSPACE")
        os.environ["PYCRAFT_WORKSPACE"] = str(self.ws_root)

    def tearDown(self):
        if self.orig_env is not None:
            os.environ["PYCRAFT_WORKSPACE"] = self.orig_env
        else:
            os.environ.pop("PYCRAFT_WORKSPACE", None)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    async def test_agent_loop_direct_text_no_tools(self):
        # Gemini answers directly without calling any tools
        mock_response = MagicMock()
        mock_response.function_calls = None
        mock_response.text = "Hello! I am PyCraft. How can I assist you today?"
        mock_response.candidates = [MagicMock(content=MagicMock(parts=[]))]

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        contents = [types.Content(role="user", parts=[types.Part.from_text(text="Hi")])]
        reply, tools, modified, modified_paths = await run_agent_loop(
            client=mock_client,
            model_name="gemini-3.5-flash-lite",
            contents=contents,
            user_prompt="Hi",
            conversation_history=[],
        )

        self.assertEqual(reply, "Hello! I am PyCraft. How can I assist you today?")
        self.assertEqual(tools, [])
        self.assertFalse(modified)
        self.assertEqual(modified_paths, [])

    async def test_agent_loop_single_tool_call_flow(self):
        # Turn 1: Gemini calls list_workspace_files
        mock_call = MagicMock()
        mock_call.name = "list_workspace_files"
        mock_call.args = {}
        mock_call.id = "call_123"

        part1 = MagicMock()
        part1.function_call = mock_call
        part1.text = None

        content1 = MagicMock()
        content1.parts = [part1]

        cand1 = MagicMock()
        cand1.content = content1

        resp1 = MagicMock()
        resp1.function_calls = [mock_call]
        resp1.candidates = [cand1]
        resp1.text = None

        # Turn 2: Gemini gives final text answer
        resp2 = MagicMock()
        resp2.function_calls = None
        resp2.text = "You have 1 file: hello.txt"
        resp2.candidates = [MagicMock(content=MagicMock(parts=[types.Part.from_text(text="You have 1 file: hello.txt")]))]

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = [resp1, resp2]

        activities = []
        async def on_activity(act):
            activities.append(act)

        contents = [types.Content(role="user", parts=[types.Part.from_text(text="What files do I have?")])]
        reply, tools, modified, modified_paths = await run_agent_loop(
            client=mock_client,
            model_name="gemini-3.5-flash-lite",
            contents=contents,
            user_prompt="What files do I have?",
            conversation_history=[],
            activity_callback=on_activity,
        )

        self.assertEqual(reply, "You have 1 file: hello.txt")
        self.assertEqual(tools, ["list_workspace_files"])
        self.assertFalse(modified)
        self.assertEqual(modified_paths, [])
        self.assertEqual(activities, ["Listing workspace files..."])

    async def test_agent_loop_write_tool_sets_modified_flag(self):
        # Gemini calls write_workspace_file for a new file
        mock_call = MagicMock()
        mock_call.name = "write_workspace_file"
        mock_call.args = {"path": "result.txt", "content": "42"}
        mock_call.id = "call_write"

        part1 = MagicMock()
        part1.function_call = mock_call
        part1.text = None

        content1 = MagicMock()
        content1.parts = [part1]

        cand1 = MagicMock()
        cand1.content = content1

        resp1 = MagicMock()
        resp1.function_calls = [mock_call]
        resp1.candidates = [cand1]

        resp2 = MagicMock()
        resp2.function_calls = None
        resp2.text = "I have created result.txt with value 42."
        resp2.candidates = [MagicMock(content=MagicMock(parts=[]))]

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = [resp1, resp2]

        contents = [types.Content(role="user", parts=[types.Part.from_text(text="Create result.txt")])]
        reply, tools, modified, modified_paths = await run_agent_loop(
            client=mock_client,
            model_name="gemini-3.5-flash-lite",
            contents=contents,
            user_prompt="Create result.txt",
            conversation_history=[],
        )

        self.assertEqual(tools, ["write_workspace_file"])
        self.assertTrue(modified)
        self.assertEqual(modified_paths, ["result.txt"])
        self.assertTrue((self.ws_root / "result.txt").exists())

    async def test_agent_loop_max_iterations_safety_guard(self):
        # Gemini perpetually requests tool calls
        mock_call = MagicMock()
        mock_call.name = "list_workspace_files"
        mock_call.args = {}
        mock_call.id = "call_loop"

        part1 = MagicMock()
        part1.function_call = mock_call
        part1.text = None

        content1 = MagicMock()
        content1.parts = [part1]

        resp = MagicMock()
        resp.function_calls = [mock_call]
        resp.candidates = [MagicMock(content=content1)]

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = resp

        contents = [types.Content(role="user", parts=[types.Part.from_text(text="Loop forever")])]
        reply, tools, modified, modified_paths = await run_agent_loop(
            client=mock_client,
            model_name="gemini-3.5-flash-lite",
            contents=contents,
            user_prompt="Loop forever",
            conversation_history=[],
        )

        self.assertIn("maximum number of tool steps", reply)
        self.assertEqual(len(tools), MAX_TOOL_ITERATIONS)
        self.assertFalse(modified)


class ChatEndpointPhase5Tests(unittest.TestCase):
    """Test FastAPI /chat endpoint with Phase 5 agent loop."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="pycraft_test_chat_")
        self.ws_root = Path(self.test_dir).resolve()
        self.orig_env = os.environ.get("PYCRAFT_WORKSPACE")
        os.environ["PYCRAFT_WORKSPACE"] = str(self.ws_root)

    def tearDown(self):
        if self.orig_env is not None:
            os.environ["PYCRAFT_WORKSPACE"] = self.orig_env
        else:
            os.environ.pop("PYCRAFT_WORKSPACE", None)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @patch("app.main.run_agent_loop")
    @patch("app.main.genai.Client")
    def test_chat_json_response_format(self, mock_client_cls, mock_agent_loop):
        # Configure mock return for agent loop
        mock_agent_loop.return_value = ("Here is your answer.", ["list_workspace_files"], False, [])

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-12345"}):
            response = self.client.post(
                "/chat",
                json={"message": "List my files", "history": []},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["reply"], "Here is your answer.")
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["tools_used"], ["list_workspace_files"])
        self.assertFalse(data["files_modified"])
        self.assertEqual(data["modified_files"], [])

    @patch("app.main.run_agent_loop")
    @patch("app.main.genai.Client")
    def test_chat_sse_streaming_response(self, mock_client_cls, mock_agent_loop):
        # Configure mock agent loop to simulate activity callback and completion
        async def fake_loop(*args, **kwargs):
            cb = kwargs.get("activity_callback")
            if cb:
                await cb("Listing workspace files...")
            return ("All done!", ["list_workspace_files"], False, [])

        mock_agent_loop.side_effect = fake_loop

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-12345"}):
            response = self.client.post(
                "/chat",
                headers={"Accept": "text/event-stream"},
                json={"message": "List files", "history": []},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers["content-type"])
        body = response.text
        self.assertIn('"type": "activity"', body)
        self.assertIn("Listing workspace files...", body)
        self.assertIn('"type": "done"', body)
        self.assertIn("All done!", body)


if __name__ == "__main__":
    unittest.main()
