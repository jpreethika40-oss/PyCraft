import asyncio
import json
import logging
import os
from pathlib import Path
from typing import AsyncGenerator
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field

from app.workspace import (
    get_workspace_root,
    list_workspace_files,
    read_workspace_file,
    write_workspace_file,
)
from app.agent import (
    run_agent_loop,
    execute_agent_tool,
    check_user_overwrite_confirmation,
)

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pycraft")

# Base directory paths
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
PROJECT_ROOT = BASE_DIR.parent
ENV_FILE = PROJECT_ROOT / ".env"

# Explicitly load .env from project root if present
load_dotenv(dotenv_path=ENV_FILE)
load_dotenv()

# Initialize/verify workspace directory exists at startup
WORKSPACE_ROOT = get_workspace_root()
logger.info(f"Initialized PyCraft workspace at: {WORKSPACE_ROOT}")

# Model configuration: default to gemini-3.5-flash-lite, with safe fallbacks
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
FALLBACK_MODELS = ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.1-flash-lite"]

app = FastAPI(
    title="PyCraft",
    description="Your Personal AI Coding Agent - Backend Server with Autonomous Workspace Tools",
    version="0.5.0",
)

# Mount the static directory for CSS, JavaScript, and assets
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Pydantic Request & Response Models
# ---------------------------------------------------------------------------

class MessageItem(BaseModel):
    role: str = Field(..., description="Message sender role: 'user' or 'model'")
    content: str = Field(..., description="Message text content")


class ChatRequest(BaseModel):
    message: str = Field(..., description="Latest message string sent by the user")
    history: list[MessageItem] = Field(default_factory=list, description="Prior conversation history")


class ChatResponse(BaseModel):
    reply: str = Field(..., description="Reply from PyCraft")
    status: str = Field(default="ok", description="Status indicator")
    tools_used: list[str] = Field(default_factory=list, description="Tools called during response generation")
    files_modified: bool = Field(default=False, description="Whether files were created or updated")
    modified_files: list[str] = Field(default_factory=list, description="Workspace-relative paths of modified files")


class FileListResponse(BaseModel):
    files: list[str] = Field(..., description="List of workspace-relative file paths")
    count: int = Field(..., description="Total count of readable files in the workspace")


class FileReadRequest(BaseModel):
    path: str = Field(..., description="Workspace-relative path to the file to read")


class FileReadResponse(BaseModel):
    path: str = Field(..., description="Workspace-relative path of the file")
    content: str = Field(..., description="Text content of the file (UTF-8)")
    size: int = Field(..., description="File size in bytes")


class FileWriteRequest(BaseModel):
    path: str = Field(..., description="Workspace-relative path to the file to create or update")
    content: str = Field(..., description="UTF-8 text content to save")
    overwrite: bool = Field(default=False, description="Whether to overwrite if file already exists")


class FileWriteResponse(BaseModel):
    path: str = Field(..., description="Workspace-relative path of the file")
    operation: str = Field(..., description="Operation performed: 'created' or 'updated'")
    bytes_written: int = Field(..., description="Number of bytes written to disk")
    status: str = Field(default="ok", description="Status indicator")


# ---------------------------------------------------------------------------
# Global Validation Exception Handler
# ---------------------------------------------------------------------------

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Provide a clean, readable error message for malformed payloads or missing fields."""
    errors_list = exc.errors()
    if errors_list:
        first_err = errors_list[0]
        field = first_err.get("loc", ["payload"])[-1]
        msg = first_err.get("msg", "Invalid field")
        detail = f"Invalid request payload for '{field}': {msg}"
    else:
        detail = "Invalid request payload."
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": detail},
    )


# ---------------------------------------------------------------------------
# Frontend Web Route
# ---------------------------------------------------------------------------

@app.get("/", response_class=FileResponse, summary="Serve chat interface")
async def serve_index():
    """Serve the PyCraft chat web page."""
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The chat web page (index.html) was not found in static files.",
        )
    return FileResponse(index_path)


# ---------------------------------------------------------------------------
# Workspace Tool Endpoints (Phase 3 & Phase 4)
# ---------------------------------------------------------------------------

def _execute_read_file(path_str: str) -> FileReadResponse:
    """Helper to read workspace file and map domain exceptions to HTTP status codes."""
    try:
        rel_path, content, size = read_workspace_file(path_str, workspace_root=get_workspace_root())
        return FileReadResponse(path=rel_path, content=content, size=size)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )
    except IsADirectoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except ValueError as exc:
        err_msg = str(exc)
        if "exceeds maximum allowed size" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=err_msg,
            )
        elif "binary data" in err_msg or "UTF-8" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=err_msg,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=err_msg,
            )
    except Exception as exc:
        logger.error(f"Unexpected error reading workspace file '{path_str}': {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while reading the workspace file.",
        )


def _execute_write_file(payload: FileWriteRequest) -> FileWriteResponse:
    """Helper to write workspace file and map domain exceptions to HTTP status codes."""
    try:
        rel_path, operation, bytes_written = write_workspace_file(
            rel_path_str=payload.path,
            content=payload.content,
            overwrite=payload.overwrite,
            workspace_root=get_workspace_root(),
        )
        return FileWriteResponse(
            path=rel_path,
            operation=operation,
            bytes_written=bytes_written,
            status="ok",
        )
    except FileExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )
    except IsADirectoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except ValueError as exc:
        err_msg = str(exc)
        if "exceeds maximum allowed file size" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=err_msg,
            )
        elif "binary" in err_msg or "UTF-8" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=err_msg,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=err_msg,
            )
    except Exception as exc:
        logger.error(f"Unexpected error writing workspace file '{payload.path}': {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while writing the workspace file.",
        )


@app.get(
    "/workspace/files",
    response_model=FileListResponse,
    summary="List readable files in workspace",
    tags=["workspace"],
)
async def list_files_endpoint():
    """
    List all readable, non-excluded text files within the configured workspace.
    Returns workspace-relative paths (using forward slashes) and the total file count.
    """
    try:
        files = list_workspace_files(workspace_root=get_workspace_root())
        return FileListResponse(files=files, count=len(files))
    except Exception as exc:
        logger.error(f"Error listing workspace files: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list workspace files.",
        )


@app.get(
    "/workspace/file",
    response_model=FileReadResponse,
    summary="Read a workspace text file (GET query param)",
    tags=["workspace"],
)
async def read_file_get_endpoint(
    path: str = Query(..., description="Workspace-relative path to the text file to read")
):
    """
    Read the contents of a UTF-8 text file from the workspace via query parameter.
    Validates containment, size limits, and UTF-8 encoding.
    """
    return _execute_read_file(path)


@app.post(
    "/workspace/read",
    response_model=FileReadResponse,
    summary="Read a workspace text file (POST JSON payload)",
    tags=["workspace"],
)
async def read_file_post_endpoint(payload: FileReadRequest):
    """
    Read the contents of a UTF-8 text file from the workspace via JSON request payload.
    Validates containment, size limits, and UTF-8 encoding.
    """
    return _execute_read_file(payload.path)


@app.post(
    "/workspace/write",
    response_model=FileWriteResponse,
    summary="Create or update a workspace text file (Phase 4)",
    tags=["workspace"],
)
async def write_file_post_endpoint(payload: FileWriteRequest):
    """
    Safely create or update a UTF-8 text file within the workspace.
    - If path does not exist, creates the file and any necessary parent directories.
    - If path exists and overwrite=false, rejects with HTTP 409 Conflict.
    - If path exists and overwrite=true, atomically replaces the file contents.
    - Strictly rejects directory traversal, out-of-boundary paths, and sensitive files.
    """
    return _execute_write_file(payload)


@app.post(
    "/workspace/file",
    response_model=FileWriteResponse,
    summary="Create or update a workspace text file (Alias)",
    tags=["workspace"],
    include_in_schema=False,
)
async def write_file_alias_endpoint(payload: FileWriteRequest):
    """Alias for POST /workspace/write."""
    return _execute_write_file(payload)


# ---------------------------------------------------------------------------
# Chat & Agent Endpoint (Phase 2 & Phase 5)
# ---------------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse, summary="Process chat message through Gemini agent loop")
async def chat_endpoint(request: Request, payload: ChatRequest):
    """
    Handle incoming chat messages through the PyCraft Gemini Agent Loop.

    Features:
    - Sends conversation and tool declarations to Gemini.
    - Autonomous tool calling with strict Python allowlist (`list_workspace_files`, `read_workspace_file`, `write_workspace_file`).
    - Enforces overwrite safety: asks for explicit confirmation before overwriting existing files.
    - Supports Server-Sent Events (SSE) streaming for real-time activity updates ("Reading hello.txt...").
    - Standard JSON response fallback for programmatic/test clients.
    """
    raw_message = payload.message
    cleaned_message = raw_message.strip()

    # 1. Validation: reject empty or whitespace-only messages
    if not cleaned_message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message cannot be empty. Please enter a question or prompt.",
        )

    # 2. Check for configured GEMINI_API_KEY (reload from .env if needed)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key and ENV_FILE.exists():
        load_dotenv(dotenv_path=ENV_FILE, override=True)
        api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not api_key:
        logger.error("GEMINI_API_KEY is not configured on the server.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The Gemini API key is not configured. Please configure GEMINI_API_KEY in your .env file or environment.",
        )

    # 3. Construct multi-turn contents list
    contents: list[types.Content] = []
    prior_turns = payload.history[-20:] if payload.history else []
    for turn in prior_turns:
        turn_text = turn.content.strip()
        if not turn_text:
            continue
        role = "user" if turn.role == "user" else "model"
        contents.append(
            types.Content(
                role=role,
                parts=[types.Part.from_text(text=turn_text)],
            )
        )

    # Append current user prompt
    contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=cleaned_message)],
        )
    )

    # 4. Model candidates and client configuration
    configured_model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip()
    models_to_try = [configured_model] + [m for m in FALLBACK_MODELS if m != configured_model]

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=60000),  # 60,000 ms = 60 seconds
    )

    # 5. Check client accept header for SSE streaming
    accept_header = request.headers.get("accept", "")
    wants_streaming = "text/event-stream" in accept_header

    if wants_streaming:
        async def event_stream() -> AsyncGenerator[str, None]:
            queue: asyncio.Queue[str] = asyncio.Queue()

            async def activity_callback(msg: str) -> None:
                await queue.put(json.dumps({"type": "activity", "activity": msg}))

            async def runner():
                last_err = None
                for model_name in models_to_try:
                    try:
                        reply, tools, modified, modified_paths = await run_agent_loop(
                            client=client,
                            model_name=model_name,
                            contents=list(contents),
                            user_prompt=cleaned_message,
                            conversation_history=prior_turns,
                            activity_callback=activity_callback,
                        )
                        await queue.put(
                            json.dumps({
                                "type": "done",
                                "reply": reply,
                                "status": "ok",
                                "tools_used": tools,
                                "files_modified": modified,
                                "modified_files": modified_paths,
                            })
                        )
                        return
                    except Exception as exc:
                        err_text = str(exc)
                        if api_key in err_text:
                            err_text = err_text.replace(api_key, "[REDACTED]")
                        logger.warning(f"Model {model_name} failed in streaming agent loop: {err_text}")
                        last_err = err_text
                        continue

                await queue.put(
                    json.dumps({
                        "type": "error",
                        "detail": last_err or "Failed to generate a response from the AI model.",
                    })
                )

            # Start runner task
            task = asyncio.create_task(runner())

            while not task.done() or not queue.empty():
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=0.2)
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    continue

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    # Non-streaming JSON response mode (Standard REST & Tests)
    last_error_detail = None
    last_status_code = status.HTTP_502_BAD_GATEWAY

    for model_name in models_to_try:
        try:
            reply, tools_used, files_modified, modified_paths = await run_agent_loop(
                client=client,
                model_name=model_name,
                contents=list(contents),
                user_prompt=cleaned_message,
                conversation_history=prior_turns,
            )
            return ChatResponse(
                reply=reply,
                status="ok",
                tools_used=tools_used,
                files_modified=files_modified,
                modified_files=modified_paths,
            )

        except (errors.APIError, errors.ClientError, errors.ServerError) as exc:
            err_text = str(exc.message) if hasattr(exc, "message") and exc.message else str(exc)
            if api_key in err_text:
                err_text = err_text.replace(api_key, "[REDACTED]")
            logger.warning(f"Model {model_name} returned error: {err_text}")

            if "401" in err_text or "INVALID_ARGUMENT" in err_text or "API_KEY_INVALID" in err_text:
                last_status_code = status.HTTP_401_UNAUTHORIZED
                last_error_detail = "Invalid or unauthorized API key. Please verify your GEMINI_API_KEY."
                break
            elif "429" in err_text or "RESOURCE_EXHAUSTED" in err_text:
                last_status_code = status.HTTP_429_TOO_MANY_REQUESTS
                last_error_detail = "Gemini rate limit reached. Please wait a few moments before trying again."
                break
            elif "404" in err_text or "NOT_FOUND" in err_text:
                last_error_detail = f"Model {model_name} is not available. Trying alternative model..."
                continue
            elif "503" in err_text or "UNAVAILABLE" in err_text or "high demand" in err_text:
                last_error_detail = "The AI service is experiencing high demand. Please try again shortly."
                continue
            else:
                last_error_detail = f"Gemini API returned an error: {err_text}"
                break

        except Exception as exc:
            err_text = str(exc)
            if api_key in err_text:
                err_text = err_text.replace(api_key, "[REDACTED]")
            logger.error(f"Error with model {model_name}: {err_text}")
            if "timed out" in err_text.lower() or "timeout" in err_text.lower():
                last_status_code = status.HTTP_504_GATEWAY_TIMEOUT
                last_error_detail = "The request to the AI model timed out. Please try again."
            else:
                last_status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
                last_error_detail = "An error occurred while contacting the AI service. Please try again."
            break

    raise HTTPException(
        status_code=last_status_code,
        detail=last_error_detail or "Unable to get a response from the AI model.",
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
