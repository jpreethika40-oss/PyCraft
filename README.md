# PyCraft: My Personal AI Coding Agent

PyCraft is an AI coding agent designed to run in a browser-based chat interface backed by Python. When fully realized, PyCraft will inspect and edit project files within a workspace to help developers write, debug, and understand code.

This project is built and documented incrementally across phases:
- **Phase 1:** Project Foundation, Web Chat Interface & FastAPI Server *(Complete)*
- **Phase 2:** Google Gemini AI Model Integration (`google-genai` SDK) & Multi-Turn Chat *(Complete)*
- **Phase 3:** Restricted Workspace Tools: Safe File Listing & Text File Reading *(Complete)*
- **Phase 4:** Restricted Workspace Tools: Safe File Creation & Atomic Updates *(Complete)*
- **Phase 5:** Autonomous Coding Agent Loop, Function Calling & Terminal Tools *(Planned)*

---

## Architecture & Technology Choices

- **Language:** Python 3.10+
- **Backend Framework:** [FastAPI](https://fastapi.tiangolo.com/) for high performance, automatic request validation, and lightweight routing.
- **ASGI Server:** [Uvicorn](https://www.uvicorn.org/) to run the FastAPI application.
- **AI SDK (Phase 2):** [google-genai](https://github.com/googleapis/python-genai) official Google GenAI Python SDK.
- **AI Model (Phase 2):** Google Gemini (`gemini-3.5-flash-lite` by default, configurable via `GEMINI_MODEL`, with automatic fallback support).
- **Workspace Security (Phases 3 & 4):** Sandboxed path containment module in `app/workspace.py` providing strict directory jail, size caps, UTF-8 encoding validation, and atomic writes.
- **Frontend:** Clean, responsive HTML5, CSS3, and modern JavaScript (no heavy frontend frameworks or build steps required).
- **Communication:** HTTP JSON endpoints (`GET /` to serve UI, `POST /chat` for conversational AI, `GET /workspace/files`, `GET /workspace/file`, `POST /workspace/read`, and `POST /workspace/write` for workspace operations).

---

## Project Structure

```text
PyCraft/
├── app/
│   ├── __init__.py           # Package marker for the app module
│   ├── main.py               # FastAPI routes, input validation & API endpoints
│   ├── workspace.py          # Workspace isolation, path containment & safe read/write tools
│   └── static/
│       ├── index.html        # Clean, responsive chat interface
│       ├── styles.css        # Modern responsive dark/light styles
│       └── app.js            # Client-side chat logic, session history & safe DOM rendering
├── workspace/                # Default isolated workspace directory for file operations
│   └── hello.txt             # Sample workspace file
├── tests/
│   └── test_workspace.py     # Automated test suite (32 tests) for workspace safeguards & endpoints
├── .env.example              # Environment variables template (GEMINI_API_KEY, GEMINI_MODEL, PYCRAFT_WORKSPACE)
├── .gitignore                # Ignores venv, caches, local .env & OS files
├── requirements.txt          # Python dependencies (fastapi, uvicorn, google-genai)
└── README.md                 # Complete project documentation and run guide
```

---

## Setup & Installation

### 1. Prerequisites
- Python 3.10 or higher installed on your machine.
- A Google Gemini API Key from [Google AI Studio](https://aistudio.google.com/) (required for Phase 2 chat).

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

> [!IMPORTANT]
> In Phase 4, these workspace tools are exposed as dedicated FastAPI endpoints for independent testing and verification. They are **not** connected to Gemini or the chat UI yet. Automated AI tool execution and the agent loop are deferred to Phase 5.

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

## Complete API Reference

### Frontend & Chat Endpoints

#### 1. `GET /`
- **Purpose:** Serves the PyCraft chat web application (`index.html`).
- **Response:** HTML web page (Status 200).

#### 2. `POST /chat`
- **Purpose:** Receives user chat message and prior conversation history, forwards to Gemini, and returns the AI reply.
- **Request Body (JSON):**
  ```json
  {
    "message": "Explain binary search in Python",
    "history": [
      {"role": "user", "content": "Hi"},
      {"role": "model", "content": "Hello! How can I help you today?"}
    ]
  }
  ```
- **Response Body (JSON - Status 200 OK):**
  ```json
  {
    "reply": "Binary search is an efficient algorithm...",
    "status": "ok"
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
- **Response Body (JSON - Status 200 OK):**
  ```json
  {
    "path": "hello.txt",
    "content": "Hello! This is a sample file inside the PyCraft workspace.\n...",
    "size": 137
  }
  ```

#### 6. `POST /workspace/write`
- **Purpose:** Safely create a new text file or update an existing text file inside the workspace.
- **Request Body (JSON):**
  ```json
  {
    "path": "docs/todo.txt",
    "content": "1. Review Phase 4\n2. Plan Phase 5",
    "overwrite": false
  }
  ```
- **Response Body (JSON - Status 200 OK):**
  ```json
  {
    "path": "docs/todo.txt",
    "operation": "created",
    "bytes_written": 35,
    "status": "ok"
  }
  ```

#### Workspace Error Responses:
- **HTTP 400 Bad Request:**
  - Path traversal: `{"detail": "Path traversal ('..') is not permitted."}`
  - Absolute path: `{"detail": "Absolute paths are not allowed. Please provide a workspace-relative path."}`
  - Directory target: `{"detail": "Path 'subfolder' is a directory, not a regular file."}`
  - Empty path: `{"detail": "File path cannot be empty."}`
- **HTTP 403 Forbidden:**
  - Workspace boundary escape / out-of-jail symlink: `{"detail": "Access denied: path resolves outside the workspace boundary."}`
  - Excluded or sensitive file (`.env`, `.git`, credentials): `{"detail": "Writing to excluded or sensitive paths is not permitted."}`
- **HTTP 404 Not Found:**
  - Non-existent file on read: `{"detail": "File not found: 'missing.txt'"}`
  - Excluded file on read: `{"detail": "The requested file is excluded or cannot be accessed."}`
- **HTTP 409 Conflict:**
  - Existing file with `overwrite: false`: `{"detail": "File 'hello.txt' already exists and overwrite is set to false."}`
- **HTTP 413 Content Too Large:**
  - Content exceeds 100 KB: `{"detail": "Content exceeds maximum allowed file size of 100 KB..."}`
- **HTTP 415 Unsupported Media Type:**
  - Binary or non-UTF-8 content: `{"detail": "Content contains binary null bytes and cannot be written as text."}`

---

## Manual Verification Guide

### 1. Start the Server
```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Verify Creating a New File (Phase 4)
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/workspace/write" `
  -Method POST `
  -Headers @{"Content-Type"="application/json"} `
  -Body '{"path": "notes.txt", "content": "Phase 4 write test successful!", "overwrite": false}' | ConvertTo-Json
```
Expected output:
```json
{
  "path": "notes.txt",
  "operation": "created",
  "bytes_written": 31,
  "status": "ok"
}
```

### 3. Verify Accidental Overwrite Protection (HTTP 409 Conflict)
Attempt to write to `notes.txt` again without setting `overwrite: true`:
```powershell
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:8000/workspace/write" `
      -Method POST `
      -Headers @{"Content-Type"="application/json"} `
      -Body '{"path": "notes.txt", "content": "Overwriting without permission", "overwrite": false}'
} catch {
    $_.Exception.Response.StatusCode.value__
    $_.ErrorDetails.Message
}
```
Expected status: `409 Conflict` ("File 'notes.txt' already exists and overwrite is set to false.")

### 4. Verify Updating an Existing File (overwrite: true)
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/workspace/write" `
  -Method POST `
  -Headers @{"Content-Type"="application/json"} `
  -Body '{"path": "notes.txt", "content": "Updated content with overwrite true", "overwrite": true}' | ConvertTo-Json
```
Expected output:
```json
{
  "path": "notes.txt",
  "operation": "updated",
  "bytes_written": 35,
  "status": "ok"
}
```

### 5. Verify Security Defense on Writes
Attempt to write to `.env`:
```powershell
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:8000/workspace/write" `
      -Method POST `
      -Headers @{"Content-Type"="application/json"} `
      -Body '{"path": ".env", "content": "LEAK=true", "overwrite": true}'
} catch {
    $_.Exception.Response.StatusCode.value__
    $_.ErrorDetails.Message
}
```
Expected status: `403 Forbidden` ("Writing to excluded or sensitive paths is not permitted.")

### 6. Run Full Automated Test Suite
Run all 32 tests (covering listing, reading, creating, updating, and all security safeguards):
```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

---

## Project Roadmap & Phase Comparison

| Capability | Phase 1 (Foundation) | Phase 2 (Gemini Chat) | Phase 3 (Read Tools) | Phase 4 (Write Tools) | Phase 5 (Agent Loop) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Web UI** | Clean chat interface | Refined product design | Unchanged (isolated) | Unchanged (isolated) | Tool status & file viewer |
| **Backend Server** | FastAPI foundation | FastAPI + `google-genai` | FastAPI + Workspace read | FastAPI + Workspace write | Agent tool orchestrator |
| **AI Integration** | Echo stub | **Live Gemini Model** | Live Gemini Model | Live Gemini Model | Autonomous tool calling |
| **Workspace Listing**| None | None | **Safe file listing** | Safe file listing | File watcher |
| **Workspace Reading**| None | None | **Jailed UTF-8 reader** | Jailed UTF-8 reader | Windowed reader |
| **Workspace Writing**| None | None | None | **Safe atomic write/update**| Autonomous code patcher |
| **Terminal / Commands**| None | None | None | None | Sandboxed CLI runner |
| **Agent Loop** | None | None | None | None | Multi-step reasoning loop |

---

## Security & Best Practices

- **Zero Secret Leakage:** The API key is read solely by the backend via environment variables. It is never exposed in frontend code, responses, logs, or repository files.
- **Strict Containment:** The workspace tools cannot be tricked into reading or writing files outside the designated workspace root via symlinks or directory traversal.
- **Sensitive File Exclusion:** Files such as `.env`, `.git`, virtual environments, and credential files cannot be read, listed, created, or modified.
- **Atomic Operations:** Interrupted writes cannot leave corrupted or empty files.
- **XSS Prevention:** All user messages and AI responses are safely injected into the DOM using `textContent`.
- **Error Redaction:** Provider and internal exceptions are sanitized before returning error details to clients.
- **Single-Origin:** Frontend assets and backend endpoints share the same FastAPI instance, eliminating CORS complexity.
