# PyCraft: My Personal AI Coding Agent

PyCraft is an AI coding agent running in a clean browser-based chat interface backed by Python. PyCraft autonomously inspects, reads, creates, and updates project files within a restricted workspace to help developers write, understand, and debug code.

This project is built and documented incrementally across phases:
- **Phase 1:** Project Foundation, Web Chat Interface & FastAPI Server *(Complete)*
- **Phase 2:** Google Gemini AI Model Integration (`google-genai` SDK) & Multi-Turn Chat *(Complete)*
- **Phase 3:** Restricted Workspace Tools: Safe File Listing & Text File Reading *(Complete)*
- **Phase 4:** Restricted Workspace Tools: Safe File Creation & Atomic Updates *(Complete)*
- **Phase 5:** Autonomous Coding Agent Loop, Function Calling & Workspace Tools *(Complete)*

---

## Architecture & Technology Choices

- **Language:** Python 3.10+
- **Backend Framework:** [FastAPI](https://fastapi.tiangolo.com/) for high performance, automatic request validation, and lightweight routing.
- **ASGI Server:** [Uvicorn](https://www.uvicorn.org/) to run the FastAPI application.
- **AI SDK (Phase 2 & 5):** [google-genai](https://github.com/googleapis/python-genai) official Google GenAI Python SDK.
- **AI Model:** Google Gemini (`gemini-3.5-flash-lite` by default, configurable via `GEMINI_MODEL`, with automatic fallback support).
- **Workspace Security (Phases 3 & 4):** Sandboxed path containment module in `app/workspace.py` providing strict directory jail, size caps, UTF-8 encoding validation, and atomic writes.
- **Agent Orchestrator (Phase 5):** Multi-turn tool execution loop in `app/agent.py` with strict tool allowlist, accidental overwrite safeguards, and Server-Sent Events (SSE) activity streaming.
- **Frontend:** Clean, responsive HTML5, CSS3, and modern JavaScript with collapsible Workspace panel, file previewer, and real-time tool activity indicators.
- **Communication:** HTTP JSON endpoints and Server-Sent Events (`GET /` to serve UI, `POST /chat` for conversational AI & SSE streaming, `GET /workspace/files`, `GET /workspace/file`, `POST /workspace/read`, and `POST /workspace/write` for workspace operations).

---

## Project Structure

```text
PyCraft/
├── app/
│   ├── __init__.py           # Package marker for the app module
│   ├── main.py               # FastAPI routes, input validation & API endpoints
│   ├── workspace.py          # Workspace isolation, path containment & safe read/write tools
│   ├── agent.py              # Autonomous agent loop, function calling & strict tool allowlist
│   └── static/
│       ├── index.html        # Clean, responsive chat interface with workspace panel
│       ├── styles.css        # Modern responsive dark/light styles & activity indicators
│       └── app.js            # Client-side chat logic, SSE streaming, file viewer & safe DOM rendering
├── workspace/                # Default isolated workspace directory for file operations
│   └── hello.txt             # Sample workspace file
├── tests/
│   ├── test_workspace.py     # Automated test suite (34 tests) for workspace safeguards & endpoints
│   └── test_agent.py         # Automated test suite (18 tests) for agent loop & tool orchestration
├── .env.example              # Environment variables template (GEMINI_API_KEY, GEMINI_MODEL, PYCRAFT_WORKSPACE)
├── .gitignore                # Ignores venv, caches, local .env & OS files
├── requirements.txt          # Python dependencies (fastapi, uvicorn, google-genai)
└── README.md                 # Complete project documentation and run guide
```

---

## Setup & Installation

### 1. Prerequisites
- Python 3.10 or higher installed on your machine.
- A Google Gemini API Key from [Google AI Studio](https://aistudio.google.com/) (required for Phase 2 chat and Phase 5 agent).

### 2. Create and Activate Virtual Environment

Open PowerShell in the `C:\PyCraft` directory:

```powershell
# Create virtual environment (if not already created)
python -m venv .venv

# Activate on Windows (PowerShell)
.\.venv\Scripts\Activate.ps1
```

*(If PowerShell restricts scripts, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first, or activate via Command Prompt with `.venv\Scripts\activate.bat`).*

### 3. Install Dependencies

Install all dependencies (FastAPI, Uvicorn, and Google GenAI SDK):
```powershell
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root:
```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
GEMINI_MODEL=gemini-3.5-flash-lite
PYCRAFT_WORKSPACE=workspace
```

---

## Phase 1: Project Foundation & Architecture

In **Phase 1**, the core client-server architecture was built and verified:
1. **Frontend Chat Interface:**
   - Single-page application with clean PyCraft branding, message history container, visible loading state (animated typing dots), and error handling.
   - Fully responsive design supporting desktop and mobile screens.
   - Strict XSS protection using DOM `textContent` rendering (never raw `innerHTML`).
2. **FastAPI Backend:**
   - Static asset serving for CSS and JavaScript.
   - Input validation rejecting empty or whitespace-only messages with HTTP 400.
   - Initial temporary stub response confirming client-server connectivity before adding external AI models.

---

## Phase 2: Google Gemini AI Model Integration

In **Phase 2**, the temporary response stub was replaced with live calls to the **Google Gemini AI model** using the official `google-genai` Python SDK.

### Architecture & Communication Flow:
```text
┌─────────────────┐       JSON POST /chat       ┌──────────────────────┐      google-genai SDK      ┌─────────────────────┐
│                 │ ──────────────────────────► │                      │ ─────────────────────────► │                     │
│  Browser Client │                             │   FastAPI Backend    │                            │  Google Gemini API  │
│ (HTML/CSS/JS)   │ ◄────────────────────────── │   (app/main.py)      │ ◄───────────────────────── │  (Cloud AI Model)   │
└─────────────────┘       JSON { reply }        └──────────────────────┘       Generated Text       └─────────────────────┘
```

1. **Security Isolation:** The browser **never** communicates with Gemini directly. The API key resides strictly in the Python backend environment, keeping credentials secure.
2. **Multi-Turn Context:** The backend accepts recent session conversation history and forwards it to Gemini so users can ask contextual follow-up questions.
3. **General Intelligence:** PyCraft answers both programming questions (Python, JavaScript, Go, Rust, C++, SQL, etc.) and general questions.
4. **Resilience & Fallbacks:** Built-in retry with fallback models (`gemini-3.5-flash-lite`, `gemini-3.8-flash`, `gemini-3.1-flash-lite`) and clear error handling for rate limits or network timeouts.
5. **Credential Sanitization:** If upstream errors occur, the backend redacts any accidental key leakage before returning error details.

---

## Phase 3 & 4: Restricted Workspace Tools

In **Phases 3 and 4**, PyCraft provides a sandboxed workspace service (`app/workspace.py`) and dedicated REST endpoints for safely listing, reading, creating, and updating text files inside the workspace.

### 1. Workspace Configuration
The workspace root directory is determined as follows:
- Configured via the `PYCRAFT_WORKSPACE` environment variable (e.g. `PYCRAFT_WORKSPACE=workspace` or `PYCRAFT_WORKSPACE=C:\custom\path`).
- If unset, it defaults to the `workspace/` folder inside the project root.
- The directory is automatically created at initialization if it does not already exist.
- Paths are always canonicalized and resolved to absolute paths internally, while all API responses return workspace-relative paths with forward slashes (`/`).

### 2. File Creation & Update Behavior (Phase 4)
- **New File Creation:** If the target path does not exist, PyCraft creates the file and any necessary parent directories inside the workspace.
- **Accidental Overwrite Protection:** If the file already exists and `overwrite` is `false` (the default), the request is rejected with **HTTP 409 Conflict**. Existing files are never silently replaced.
- **Explicit Content Updates:** If the file exists and `overwrite` is `true`, its contents are safely replaced.
- **Atomic Writes:** All writes are performed atomically. Content is written to a temporary file (`.tmp_*`) in the target's parent directory, flushed and synced to disk, and then swapped using `os.replace`. An interrupted write will never corrupt or leave a partially written file.

### 3. File Access Safeguards & Security Model
All read and write operations in `app/workspace.py` strictly enforce defense-in-depth protections:

- **Strict Containment (Jail):** All target paths are resolved canonical paths validated against `resolved_path.relative_to(workspace_root)`. Any path attempting to resolve outside the workspace root raises `PermissionError` (mapped to **HTTP 403 Forbidden**).
- **Symlink Protection:** Directory symlinks are never descended into during listing. Symlinks pointing outside the workspace boundary are rejected (HTTP 403).
- **Directory Traversal Blocking:** Any path containing `..` or relative parent navigation is rejected immediately (mapped to **HTTP 400 Bad Request**).
- **Absolute Path Rejection:** Paths beginning with `/`, `\`, or Windows drive letters (e.g., `C:`) are rejected (HTTP 400). Only workspace-relative paths are accepted.
- **Sensitive & Secret Exclusions:** Consistently across listing, reading, and writing, the following are strictly excluded:
  - Hidden files/directories (starting with `.`, such as `.git`, `.env`, `.vscode`, `.idea`)
  - Virtual environments (`.venv`, `venv`, `env`, `ENV`, `node_modules`)
  - Python caches (`__pycache__`, `*.pyc`, `*.pyo`, `.pytest_cache`)
  - Credential files and keys (`id_rsa`, `*credentials*`, `*secrets*`, `*token*`, `*.pem`, `*.key`)
  - Binary and archive extensions (`.exe`, `.dll`, `.bin`, `.zip`, `.tar`, `.pdf`, `.png`, `.jpg`, etc.)
  - On write, targeting excluded files returns **HTTP 403 Forbidden**. On read, they return **HTTP 404 Not Found**.
- **File Size Limit (100 KB):** Reading or writing files larger than 100 KB (102,400 bytes) is rejected with **HTTP 413 Content Too Large** to protect memory and token context.
- **Text & UTF-8 Encoding Validation:** Files or payloads containing binary null bytes (`\x00`) or non-UTF-8 bytes are rejected with **HTTP 415 Unsupported Media Type**.
- **Directory Access Prevention:** Requesting a directory path to read or write returns **HTTP 400 Bad Request** ("Path is a directory, not a regular file").
- **No Path Leakage:** Only relative, normalized paths (e.g. `hello.txt` or `docs/sample.txt`) are returned in API responses; host absolute paths are never leaked.

---

## Phase 5: Autonomous Coding Agent Loop & Function Calling

In **Phase 5**, PyCraft connects Google Gemini directly to its sandboxed workspace file tools via an autonomous multi-turn agent loop (`app/agent.py`).

### Agent Loop Workflow:
```text
  User Message
       │
       ▼
┌──────────────┐
│  FastAPI     │ ────► Initializes Google GenAI Client with tools & conversation
│  /chat route │
└──────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────────────────────┐
│                          Agent Loop (Max 6 Iterations)                 │
│                                                                        │
│   1. Model Generation: Gemini analyzes context and tool declarations    │
│                                                                        │
│   2. Tool Call Requested?                                              │
│        ├─ NO  ──► Extract final text answer ──► Return to user         │
│        │                                                               │
│        └─ YES ──► Check tool allowlist:                                 │
│                   - list_workspace_files                               │
│                   - read_workspace_file                                │
│                   - write_workspace_file                               │
│                   Broadcast activity update (SSE)                      │
│                   Execute approved Python workspace function           │
│                   Format FunctionResponse (role="user")                │
│                   Append response to contents ──► Loop back to step 1  │
└────────────────────────────────────────────────────────────────────────┘
```

### Key Capabilities & Safeguards:

1. **Strict Tool Allowlist (`TOOL_ALLOWLIST`):**
   Only three approved Python functions are exposed to the model:
   - `list_workspace_files`: list relative paths of readable text files.
   - `read_workspace_file`: read UTF-8 content of a workspace-relative file.
   - `write_workspace_file`: create or update a UTF-8 text file.
   Any unapproved function or arbitrary code execution request is immediately rejected.

2. **Accidental Overwrite Confirmation Rule:**
   The agent will **never** silently overwrite an existing file. If the model attempts to write to a path that already exists in the workspace, `check_user_overwrite_confirmation` verifies whether the user explicitly authorized replacing that file. A tool argument alone (`overwrite: true` generated by the model) is NOT sufficient. If unconfirmed, the tool returns a conflict status, and the agent asks the user for explicit confirmation before overwriting.

3. **Real-Time Activity Indicators (SSE Streaming):**
   When the browser client connects using `Accept: text/event-stream`, the agent loop streams live activity updates (e.g. *"Listing workspace files..."*, *"Reading hello.txt..."*, *"Writing notes.txt..."*) directly into the chat bubble, replacing the generic typing dots with transparent progress.

4. **Automatic Workspace Panel Synchronization:**
   Whenever the agent loop creates or updates a file (`files_modified = True`), the chat UI automatically triggers a refresh of the Workspace file list so the user immediately sees the changes.

5. **Loop Termination Protection:**
   The agent loop enforces `MAX_TOOL_ITERATIONS = 6` to prevent runaway or looping tool calls, terminating gracefully if a model exceeds the threshold.

---

## Complete API Reference

### Frontend & Chat Endpoints

#### 1. `GET /`
- **Purpose:** Serves the PyCraft chat web application (`index.html`).
- **Response:** HTML web page (Status 200).

#### 2. `POST /chat`
- **Purpose:** Receives user chat message and prior conversation history, executes the multi-turn agent loop with Gemini and workspace tools, and returns the AI reply.
- **Headers:**
  - `Accept: text/event-stream` (optional): Stream real-time activity events and final response via Server-Sent Events.
  - `Accept: application/json` (default): Return standard JSON response.
- **Request Body (JSON):**
  ```json
  {
    "message": "List my workspace files and tell me what is inside hello.txt",
    "history": [
      {"role": "user", "content": "Hi"},
      {"role": "model", "content": "Hello! How can I help you today?"}
    ]
  }
  ```
- **Response Body (JSON - Status 200 OK):**
  ```json
  {
    "reply": "Your workspace contains hello.txt. Inside, it says: ...",
    "status": "ok",
    "tools_used": ["list_workspace_files", "read_workspace_file"],
    "files_modified": false
  }
  ```

### Workspace Tool Endpoints (Phase 3 & Phase 4)

#### 3. `GET /workspace/files`
- **Purpose:** List all readable, non-excluded text files inside the workspace.
- **Response Body (JSON - Status 200 OK):**
  ```json
  {
    "files": [
      "hello.txt",
      "docs/notes.txt"
    ],
    "count": 2
  }
  ```

#### 4. `GET /workspace/file?path={relative_path}`
- **Purpose:** Read the text content of a workspace file via query parameter.
- **Parameters:**
  - `path` (string, required): Workspace-relative path to the file (e.g. `hello.txt`).
- **Response Body (JSON - Status 200 OK):**
  ```json
  {
    "path": "hello.txt",
    "content": "Hello! This is a sample file inside the PyCraft workspace.\n...",
    "size": 137
  }
  ```

#### 5. `POST /workspace/read`
- **Purpose:** Read the text content of a workspace file via JSON request payload.
- **Request Body (JSON):**
  ```json
  {
    "path": "hello.txt"
  }
  ```

#### 6. `POST /workspace/write`
- **Purpose:** Safely create a new text file or update an existing text file inside the workspace.
- **Request Body (JSON):**
  ```json
  {
    "path": "notes.txt",
    "content": "PyCraft agent working smoothly!",
    "overwrite": false
  }
  ```
- **Response Body (JSON - Status 200 OK):**
  ```json
  {
    "path": "notes.txt",
    "operation": "created",
    "bytes_written": 32,
    "status": "ok"
  }
  ```

---

## Manual Verification Guide

### 1. Start the Server
```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Open your browser to: **`http://127.0.0.1:8000/`**

### 2. Test Autonomous Tool Calling via Browser Chat

Try asking PyCraft the following prompts in the chat:
1. **List Workspace Files:**
   > *"What files do I have in my workspace?"*
   - PyCraft will display *"Listing workspace files..."* in the typing indicator, call `list_workspace_files`, and reply with the list of files (`hello.txt`).

2. **Read Workspace File:**
   > *"What is written inside hello.txt?"*
   - PyCraft will display *"Reading hello.txt..."*, call `read_workspace_file`, and explain the content.

3. **Create a New File:**
   > *"Create a file named todo.txt with a list of 3 items for a coding project."*
   - PyCraft will display *"Writing todo.txt..."*, create the file in the workspace, and automatically refresh the Workspace panel to show `todo.txt`.

4. **Accidental Overwrite Protection:**
   > *"Save the word Test into hello.txt."*
   - PyCraft will inspect the file, note that `hello.txt` already exists, and ask you for confirmation: *"The file 'hello.txt' already exists in the workspace. Would you like to overwrite it?"*
   - Replying *"Yes, overwrite it"* will proceed with the update.

### 3. Run Full Automated Test Suite
Run all 52 automated unit and integration tests across all phases:
```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

---

## Project Roadmap & Phase Comparison

| Capability | Phase 1 (Foundation) | Phase 2 (Gemini Chat) | Phase 3 (Read Tools) | Phase 4 (Write Tools) | Phase 5 (Agent Loop) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Web UI** | Clean chat interface | Refined product design | Unchanged (isolated) | Workspace panel & previewer | **Real-time activity & auto-refresh** |
| **Backend Server** | FastAPI foundation | FastAPI + `google-genai` | FastAPI + Workspace read | FastAPI + Workspace write | **Agent orchestrator & SSE streaming** |
| **AI Integration** | Echo stub | Live Gemini Model | Live Gemini Model | Live Gemini Model | **Autonomous tool calling** |
| **Workspace Listing**| None | None | Safe file listing | Safe file listing | **Autonomous `list_workspace_files`** |
| **Workspace Reading**| None | None | Jailed UTF-8 reader | Jailed UTF-8 reader | **Autonomous `read_workspace_file`** |
| **Workspace Writing**| None | None | None | Safe atomic write/update | **Autonomous `write_workspace_file`** |
| **Overwrite Safety** | None | None | None | HTTP 409 Conflict check | **Explicit user confirmation check** |
| **Safety Limits** | None | None | 100 KB limit | 100 KB limit | **Max 6 iterations limit + tool allowlist** |
| **Agent Loop** | None | None | None | None | **Multi-turn reasoning & tool loop** |

---

## Security & Best Practices

- **Zero Secret Leakage:** The API key is read solely by the backend via environment variables. It is never exposed in frontend code, responses, logs, or repository files.
- **Strict Containment:** The workspace tools cannot be tricked into reading or writing files outside the designated workspace root via symlinks or directory traversal.
- **Strict Allowlist:** The agent can only execute functions registered in `TOOL_ALLOWLIST`. Unknown tool calls, shell execution, or arbitrary command execution are strictly rejected.
- **Accidental Data Loss Prevention:** Existing files cannot be replaced without explicit confirmation from the user.
- **Atomic Operations:** Interrupted writes cannot leave corrupted or empty files.
- **XSS Prevention:** All user messages, file contents, and AI responses are safely injected into the DOM using `textContent`.
- **Single-Origin:** Frontend assets and backend endpoints share the same FastAPI instance, eliminating CORS complexity.
