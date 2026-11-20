"""PyCraft Agent Loop and Tool Orchestration.

This module provides the autonomous tool-calling loop connecting Google Gemini
to PyCraft's sandboxed workspace tools (listing, reading, creating, and updating files).
"""

import logging
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple
from google.genai import types

from app.workspace import (
    get_workspace_root,
    list_workspace_files,
    read_workspace_file,
    write_workspace_file,
    delete_workspace_file,
    validate_and_resolve_path,
)

logger = logging.getLogger("pycraft.agent")

# Maximum permitted tool iterations per conversation turn to prevent infinite loops
MAX_TOOL_ITERATIONS = 6

# Strict Python allowlist of permissible tools
TOOL_ALLOWLIST = {
    "list_workspace_files",
    "read_workspace_file",
    "write_workspace_file",
    "delete_workspace_file",
}


def get_tool_declarations() -> List[types.FunctionDeclaration]:
    """Return the official Google GenAI tool declarations for PyCraft workspace tools."""
    return [
        types.FunctionDeclaration(
            name="list_workspace_files",
            description=(
                "List all readable, non-excluded text files currently inside the workspace. "
                "Returns a list of workspace-relative paths and the total count. "
                "Always call this when the user asks what files exist or wants to explore the project."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={},
            ),
        ),
        types.FunctionDeclaration(
            name="read_workspace_file",
            description=(
                "Read the complete UTF-8 text content of a file inside the workspace. "
                "Path must be a workspace-relative path (e.g., 'hello.txt' or 'docs/notes.txt'). "
                "Absolute paths, traversal ('..'), and excluded files (.env, .git, credentials) are rejected."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "path": types.Schema(
                        type=types.Type.STRING,
                        description="Workspace-relative path to the text file to read.",
                    ),
                },
                required=["path"],
            ),
        ),
        types.FunctionDeclaration(
            name="write_workspace_file",
            description=(
                "Create a new text file or update an existing text file inside the workspace with UTF-8 text. "
                "Parent directories are created automatically inside the workspace if needed. "
                "If the file already exists, overwrite must be set to true ONLY if the user has explicitly "
                "confirmed or requested replacing that specific file."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "path": types.Schema(
                        type=types.Type.STRING,
                        description="Workspace-relative path of the file to create or update (e.g. 'notes.txt').",
                    ),
                    "content": types.Schema(
                        type=types.Type.STRING,
                        description="The complete UTF-8 text content to save into the file.",
                    ),
                    "overwrite": types.Schema(
                        type=types.Type.BOOLEAN,
                        description="Whether to overwrite if file exists. Set true only if the user explicitly confirmed overwriting.",
                    ),
                },
                required=["path", "content"],
            ),
        ),
        types.FunctionDeclaration(
            name="delete_workspace_file",
            description=(
                "Delete a single regular file inside the configured workspace. "
                "Path must be a workspace-relative path (e.g., 'temp.txt' or 'src/old.py'). "
                "Directories, absolute paths, traversal ('..'), and excluded/sensitive files cannot be deleted. "
                "CRITICAL SAFETY RULE: You must NEVER delete a file unless the user has explicitly confirmed "
                "deleting that exact file. If confirmation has not been given, ask the user: "
                "'Delete `{path}`? This cannot be undone.' and wait for explicit confirmation."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "path": types.Schema(
                        type=types.Type.STRING,
                        description="Workspace-relative path of the file to delete.",
                    ),
                },
                required=["path"],
            ),
        ),
    ]


def get_activity_description(tool_name: str, tool_args: Dict[str, Any]) -> str:
    """Generate a clean, user-friendly activity message while a tool is executing."""
    path = tool_args.get("path", "")
    if tool_name == "list_workspace_files":
        return "Listing workspace files..."
    elif tool_name == "read_workspace_file":
        return f"Reading {path}..." if path else "Reading workspace file..."
    elif tool_name == "write_workspace_file":
        return f"Writing {path}..." if path else "Writing workspace file..."
    elif tool_name == "delete_workspace_file":
        return f"Deleting {path}..." if path else "Deleting workspace file..."
    return f"Running {tool_name}..."


def check_user_overwrite_confirmation(
    target_path_str: str,
    user_prompt: str,
    conversation_history: List[Any],
) -> bool:
    """
    Verify whether the user explicitly authorized overwriting an existing file.
    A tool argument alone (e.g. overwrite=True from the model) is NOT sufficient.

    Rules:
    1. If the user's current message contains explicit overwrite/replace/update keywords.
    2. If the previous assistant turn asked for confirmation to overwrite/replace and
       the user replied with an affirmative confirmation (e.g. 'yes', 'sure', 'proceed').
    """
    clean_prompt = user_prompt.lower()
    target_leaf = Path(target_path_str).name.lower()

    # Rule 1: User explicitly directed an overwrite/replace in current prompt
    direct_overwrite_terms = ["overwrite", "replace", "update", "rewrite"]
    if any(term in clean_prompt for term in direct_overwrite_terms):
        return True

    # Rule 2: Assistant previously asked if the file could be overwritten, and user agreed
    if conversation_history:
        last_turn = conversation_history[-1]
        last_role = getattr(last_turn, "role", "")
        last_content = getattr(last_turn, "content", "").lower()

        if last_role in ("model", "assistant") and any(
            t in last_content for t in ["already exists", "overwrite", "replace"]
        ):
            affirmative_words = {
                "yes", "yep", "yeah", "sure", "ok", "okay",
                "proceed", "go ahead", "confirm", "do it",
                "please do", "overwrite it", "replace it",
            }
            # Check prompt words or phrases
            words = [w.strip(".,!?\"'") for w in clean_prompt.split()]
            if any(w in affirmative_words for w in words) or any(
                phrase in clean_prompt for phrase in ["go ahead", "please do", "overwrite it", "replace it"]
            ):
                return True

    return False


def check_user_delete_confirmation(
    target_path_str: str,
    user_prompt: str,
    conversation_history: List[Any],
) -> Tuple[bool, bool]:
    """
    Verify whether the user explicitly authorized or declined deleting an existing file.
    A tool argument alone (e.g. from the model) is NOT sufficient.

    Returns:
        Tuple of (is_confirmed, is_declined).
    """
    clean_prompt = user_prompt.lower().strip()
    target_leaf = Path(target_path_str).name.lower()
    target_posix = target_path_str.lower().replace("\\", "/")

    # Rule 1: Decline keywords
    decline_words = {
        "no", "nope", "cancel", "stop", "nevermind", "abort",
        "don't", "dont", "leave it", "keep it",
    }
    prompt_words = [w.strip(".,!?\"'") for w in clean_prompt.split()]
    if any(w in decline_words for w in prompt_words) or any(
        phrase in clean_prompt for phrase in [
            "do not delete", "don't delete", "keep it", "leave it", "cancel deletion", "no cancel"
        ]
    ):
        if conversation_history:
            last_turn = conversation_history[-1]
            last_content = getattr(last_turn, "content", "").lower()
            if "delete" in last_content and ("cannot be undone" in last_content or target_leaf in last_content or "confirm" in last_content):
                return False, True

    # Rule 2: Affirmative confirmation following an assistant confirmation prompt
    if conversation_history:
        last_turn = conversation_history[-1]
        last_role = getattr(last_turn, "role", "")
        last_content = getattr(last_turn, "content", "").lower()

        if last_role in ("model", "assistant") and "delete" in last_content:
            if target_leaf in last_content or target_posix in last_content or "cannot be undone" in last_content or "confirm" in last_content:
                affirmative_words = {
                    "yes", "yep", "yeah", "sure", "ok", "okay",
                    "proceed", "go ahead", "confirm", "do it",
                    "please do", "delete it", "delete file", "delete",
                }
                if any(w in affirmative_words for w in prompt_words) or any(
                    phrase in clean_prompt for phrase in [
                        "go ahead", "please do", "delete it", "delete file",
                        "yes delete", "yes, delete", "confirm delete", "i confirm"
                    ]
                ):
                    return True, False

    return False, False


def execute_agent_tool(
    name: str,
    args: Dict[str, Any],
    user_prompt: str,
    conversation_history: List[Any],
) -> Dict[str, Any]:
    """
    Validate and execute a single tool through the strict allowlist.
    Never executes model-generated shell/arbitrary code.
    Reuses existing Phase 3 and Phase 4 workspace functions.
    """
    # 1. Allowlist enforcement
    if name not in TOOL_ALLOWLIST:
        logger.warning(f"Rejected unapproved tool execution: {name}")
        return {"error": f"Tool '{name}' is not permitted or does not exist."}

    # 2. Tool: list_workspace_files
    if name == "list_workspace_files":
        try:
            files = list_workspace_files()
            return {"files": files, "count": len(files)}
        except Exception as exc:
            return {"error": str(exc)}

    # 3. Tool: read_workspace_file
    elif name == "read_workspace_file":
        path = args.get("path")
        if not path or not isinstance(path, str):
            return {"error": "Invalid argument: 'path' must be a non-empty string."}
        try:
            workspace_root = get_workspace_root()
            rel_path, content, size = read_workspace_file(path, workspace_root=workspace_root)
            return {"path": rel_path, "content": content, "size": size}
        except Exception as exc:
            return {"error": str(exc)}

    # 4. Tool: write_workspace_file
    elif name == "write_workspace_file":
        path = args.get("path")
        content = args.get("content")

        if not path or not isinstance(path, str):
            return {"error": "Invalid argument: 'path' must be a non-empty string."}
        if content is None or not isinstance(content, str):
            return {"error": "Invalid argument: 'content' must be a text string."}

        workspace_root = get_workspace_root()

        # Validate path syntax and containment
        try:
            target_path = validate_and_resolve_path(path, workspace_root=workspace_root, for_write=True)
        except Exception as exc:
            return {"error": str(exc)}

        # Overwrite safety check: existing files require explicit user confirmation
        if target_path.exists():
            user_confirmed = check_user_overwrite_confirmation(path, user_prompt, conversation_history)
            if not user_confirmed:
                rel_name = target_path.relative_to(workspace_root.resolve()).as_posix()
                logger.info(f"Write blocked for '{rel_name}': awaiting user confirmation to overwrite.")
                return {
                    "status": "conflict",
                    "error": "conflict",
                    "message": (
                        f"The file '{rel_name}' already exists in the workspace. "
                        "To prevent accidental data loss, ask the user for explicit confirmation "
                        f"before overwriting '{rel_name}'."
                    ),
                }
            actual_overwrite = True
        else:
            actual_overwrite = False

        try:
            rel_path, operation, size = write_workspace_file(
                rel_path_str=path,
                content=content,
                overwrite=actual_overwrite,
                workspace_root=workspace_root,
            )
            return {
                "status": "success",
                "operation": operation,
                "path": rel_path,
                "bytes_written": size,
            }
        except Exception as exc:
            return {"error": str(exc)}

    # 5. Tool: delete_workspace_file
    elif name == "delete_workspace_file":
        path = args.get("path")
        if not path or not isinstance(path, str):
            return {"error": "Invalid argument: 'path' must be a non-empty string."}

        workspace_root = get_workspace_root()

        # Validate path syntax and containment
        try:
            target_path = validate_and_resolve_path(path, workspace_root=workspace_root, for_delete=True)
        except FileNotFoundError as exc:
            return {
                "status": "not_found",
                "error": "not_found",
                "message": f"File not found: '{path}'. Cannot delete a file that does not exist.",
            }
        except Exception as exc:
            return {"error": str(exc)}

        rel_name = target_path.relative_to(workspace_root.resolve()).as_posix()

        # Check confirmation state
        is_confirmed, is_declined = check_user_delete_confirmation(
            target_path_str=rel_name,
            user_prompt=user_prompt,
            conversation_history=conversation_history,
        )

        if is_declined:
            logger.info(f"Deletion cancelled for '{rel_name}': user declined confirmation.")
            return {
                "status": "cancelled",
                "path": rel_name,
                "message": f"Deletion cancelled. The file '{rel_name}' was not deleted and remains untouched.",
            }

        if not is_confirmed:
            logger.info(f"Delete blocked for '{rel_name}': awaiting user confirmation.")
            return {
                "status": "confirmation_required",
                "path": rel_name,
                "message": (
                    f"Delete '{rel_name}'? This cannot be undone. "
                    "Ask the user for explicit confirmation before deleting this file. "
                    "Do not delete or claim the file was deleted until the user confirms."
                ),
            }

        # User explicitly confirmed: execute deletion
        try:
            deleted_path, success = delete_workspace_file(rel_name, workspace_root=workspace_root)
            return {
                "status": "success",
                "operation": "deleted",
                "path": deleted_path,
                "message": f"Successfully deleted '{deleted_path}'.",
            }
        except Exception as exc:
            return {"error": str(exc)}

    return {"error": f"Unhandled tool '{name}'."}


class AgentLoopResult(tuple):
    """
    Backwards-compatible tuple representing agent loop results.
    Unpacks as 4 elements (reply, tools_used, files_modified, modified_paths)
    for existing callers, while exposing .files_deleted and .deleted_files properties.
    """
    def __new__(
        cls,
        reply: str,
        tools_used: List[str],
        files_modified: bool,
        modified_paths: List[str],
        files_deleted: bool = False,
        deleted_files: Optional[List[str]] = None,
    ):
        inst = super().__new__(cls, (reply, tools_used, files_modified, modified_paths))
        inst.reply = reply
        inst.tools_used = tools_used
        inst.files_modified = files_modified
        inst.modified_paths = modified_paths
        inst.files_deleted = files_deleted
        inst.deleted_files = deleted_files or []
        return inst


async def run_agent_loop(
    client: Any,
    model_name: str,
    contents: List[types.Content],
    user_prompt: str,
    conversation_history: List[Any],
    activity_callback: Optional[Callable[[str], Coroutine[Any, Any, None]]] = None,
) -> AgentLoopResult:
    """
    Execute the multi-turn agent tool-calling loop with Google Gemini.

    Returns:
        AgentLoopResult (unpacks as 4-tuple: final_reply_text, tools_used_list, files_modified_bool, modified_files_list)
    """
    import asyncio

    tools_used: List[str] = []
    files_modified: bool = False
    files_deleted: bool = False
    modified_paths: List[str] = []
    deleted_paths: List[str] = []
    iterations: int = 0

    tool_declarations = get_tool_declarations()
    config = types.GenerateContentConfig(
        system_instruction=(
            "You are PyCraft, a helpful, intelligent AI coding assistant with access to an isolated workspace. "
            "You answer general questions and write code across all languages. "
            "You have tools to list files, read files, write files, and delete files in the workspace. "
            "When the user asks about project or workspace files, inspect them using your tools instead of guessing. "
            "Never claim you listed, read, created, updated, or deleted a file unless the tool succeeded. "
            "If a write fails with an error or conflict, report the exact error to the user and do not claim the file was created or updated. "
            "If a write fails with a conflict because a file already exists, clearly tell the user which file exists "
            "and ask if they would like to overwrite it before proceeding. "
            "For deletion: you must NEVER delete a file without explicit user confirmation. "
            "When asked to delete a file, ask the user clearly: 'Delete `{path}`? This cannot be undone.' "
            "Only proceed with deletion after the user explicitly confirms for that exact file. "
            "If the user declines or cancels, do not delete the file and inform the user that deletion was cancelled."
        ),
        tools=[types.Tool(function_declarations=tool_declarations)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    while iterations < MAX_TOOL_ITERATIONS:
        iterations += 1
        logger.info(f"Agent loop iteration {iterations}/{MAX_TOOL_ITERATIONS} calling model {model_name}")

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=model_name,
            contents=contents,
            config=config,
        )

        # Detect function calls in response
        function_calls = getattr(response, "function_calls", None)
        if not function_calls and response.candidates and response.candidates[0].content:
            parts = response.candidates[0].content.parts or []
            function_calls = [p.function_call for p in parts if getattr(p, "function_call", None)]

        # If no tool calls requested, we have reached the final answer
        if not function_calls:
            final_reply = response.text or ""
            if not final_reply and response.candidates and response.candidates[0].content:
                parts_text = "".join(p.text for p in response.candidates[0].content.parts if p.text)
                if parts_text.strip():
                    final_reply = parts_text.strip()

            if not final_reply.strip():
                final_reply = "I completed the request, but returned an empty response. Please let me know if you need anything else."

            return AgentLoopResult(
                final_reply.strip(),
                tools_used,
                files_modified,
                modified_paths,
                files_deleted=files_deleted,
                deleted_files=deleted_paths,
            )

        # Append model's tool call turn to contents
        model_content = response.candidates[0].content
        contents.append(model_content)

        # Execute each function call and collect tool response parts
        tool_response_parts = []
        for call in function_calls:
            tool_name = call.name
            tool_args = dict(call.args) if call.args else {}

            activity_msg = get_activity_description(tool_name, tool_args)
            if activity_callback:
                try:
                    await activity_callback(activity_msg)
                except Exception as cb_err:
                    logger.debug(f"Activity callback error: {cb_err}")

            tool_result = execute_agent_tool(
                name=tool_name,
                args=tool_args,
                user_prompt=user_prompt,
                conversation_history=conversation_history,
            )
            tools_used.append(tool_name)

            if tool_name == "write_workspace_file" and tool_result.get("status") in ("success", "created", "updated"):
                files_modified = True
                written_path = tool_result.get("path")
                if written_path and written_path not in modified_paths:
                    modified_paths.append(written_path)
            elif tool_name == "delete_workspace_file" and tool_result.get("status") == "success":
                files_modified = True
                files_deleted = True
                deleted_path = tool_result.get("path")
                if deleted_path and deleted_path not in deleted_paths:
                    deleted_paths.append(deleted_path)
                if deleted_path and deleted_path not in modified_paths:
                    modified_paths.append(deleted_path)

            tool_response_parts.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=tool_name,
                        response=tool_result,
                        id=getattr(call, "id", None),
                    )
                )
            )

        # Append tool responses as 'user' role with function_response parts to contents
        contents.append(
            types.Content(
                role="user",
                parts=tool_response_parts,
            )
        )

    # Reached maximum tool iterations
    logger.warning(f"Agent loop reached maximum tool iterations ({MAX_TOOL_ITERATIONS})")
    return AgentLoopResult(
        "I reached the maximum number of tool steps for this request. Please review the current workspace files or ask a more specific question.",
        tools_used,
        files_modified,
        modified_paths,
        files_deleted=files_deleted,
        deleted_files=deleted_paths,
    )
