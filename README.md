# PyCraft: My Personal AI Coding Agent

PyCraft is an AI coding agent designed to run in a browser-based chat interface backed by Python. When fully realized, PyCraft will inspect and edit project files within a workspace to help developers write, debug, and understand code.

This project is built and documented incrementally across phases:
- **Phase 1:** Project Foundation, Web Chat Interface & FastAPI Server
- **Phase 2:** Google Gemini AI Model Integration (`google-genai` SDK)
- **Phase 3:** Workspace File Inspection & Editing Tools *(Planned)*
- **Phase 4:** Autonomous Coding Agent Loop *(Planned)*

---

## Architecture & Technology Choices

- **Language:** Python 3.10+
- **Backend Framework:** [FastAPI](https://fastapi.tiangolo.com/) for high performance, automatic request validation, and lightweight routing.
- **ASGI Server:** [Uvicorn](https://www.uvicorn.org/) to run the FastAPI application.
- **AI SDK (Phase 2):** [google-genai](https://github.com/googleapis/python-genai) official Google GenAI Python SDK.
- **AI Model (Phase 2):** Google Gemini (`gemini-2.5-flash` by default, configurable via `GEMINI_MODEL`).
- **Frontend:** Plain HTML5, CSS3, and modern JavaScript (no heavy frontend frameworks or build steps required).
- **Communication:** HTTP JSON endpoints (`GET /` to serve UI, `POST /chat` to process messages).

---

## Project Structure

```text
PyCraft/
├── app/
│   ├── __init__.py           # Package marker for the app module
│   ├── main.py               # FastAPI routes, input validation & Gemini AI integration
│   └── static/
│       ├── index.html        # Clean, responsive chat interface
│       ├── styles.css        # Modern responsive dark/light styles
│       └── app.js            # Client-side chat logic, safe DOM rendering & error handling
├── .env.example              # Environment variables template (GEMINI_API_KEY, GEMINI_MODEL)
├── .gitignore                # Ignores venv, caches, local .env & OS files
├── requirements.txt          # Python dependencies (fastapi, uvicorn, google-genai)
└── README.md                 # Complete project documentation and run guide
```

---

## Setup & Installation

### 1. Prerequisites
- Python 3.10 or higher installed on your machine.
- A Google Gemini API Key from [Google AI Studio](https://aistudio.google.com/) (required for Phase 2).

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
   - Single-page application with PyCraft branding, message history container, visible loading state (animated typing dots), and error banners.
   - Fully responsive design supporting desktop and mobile screens.
   - Strict XSS protection using DOM `textContent` rendering (never raw `innerHTML`).
2. **FastAPI Backend:**
   - Static asset serving for CSS and JavaScript.
   - Input validation rejecting empty or whitespace-only messages with HTTP 400.
   - Initial temporary stub response confirming client-server connectivity before adding external AI models.

### Phase 1 API Behavior:
- **`GET /`** &rarr; Serves `index.html`.
- **`POST /chat`** &rarr; Accepts `{"message": "..."}`, validates input, and returned a temporary confirmation stub:
  ```json
  {
    "reply": "[PyCraft Phase 1 Temporary Reply] Received: \"...\". The AI model will be connected in a later phase.",
    "status": "ok"
  }
  ```

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
2. **Asynchronous Execution:** Calls to Gemini are made asynchronously via `client.aio.models.generate_content`, keeping the FastAPI event loop responsive.
3. **Credential Sanitization:** If upstream errors occur, the backend redacts any accidental key leakage before returning error details to the browser.

### Configuring the Gemini API Key:

You can configure the key using either of these approaches:

#### Approach A: Set in current PowerShell session (Recommended)
```powershell
$env:GEMINI_API_KEY = "your_actual_api_key_here"
```
*(Optional) Configure a specific model:*
```powershell
$env:GEMINI_MODEL = "gemini-2.5-flash"
```

#### Approach B: Use a local `.env` file
1. Copy `.env.example` to `.env`:
   ```powershell
   Copy-Item .env.example .env
   ```
2. Open `.env` and insert your key:
   ```env
   GEMINI_API_KEY=your_actual_api_key_here
   GEMINI_MODEL=gemini-3.5-flash-lite
   ```
   *(Note: `.env` is listed in `.gitignore` and is never committed to Git).*

---

## Running the Application

Start the server using Uvicorn:
```powershell
uvicorn app.main:app --reload
```
Or directly via the virtual environment's Python executable:
```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open your browser to:
```
http://127.0.0.1:8000
```

---

## Complete API Reference

### 1. `GET /`
- **Purpose:** Serves the PyCraft chat web application (`index.html`).
- **Response:** HTML web page (Status 200).

### 2. `POST /chat`
- **Purpose:** Receives user chat message, validates input, queries Gemini, and returns the AI reply.
- **Request Body (JSON):**
  ```json
  {
    "message": "Explain binary search in Python"
  }
  ```
- **Response Body (JSON - Status 200 OK):**
  ```json
  {
    "reply": "Binary search is an efficient algorithm for finding an item from a sorted list...",
    "status": "ok"
  }
  ```
- **Error Responses:**
  - **HTTP 400 Bad Request:** Message is empty or contains only whitespace (`{"detail": "Message cannot be empty. Please type a message before sending."}`).
  - **HTTP 422 Unprocessable Entity:** Request payload is malformed or missing the `message` field.
  - **HTTP 500 Internal Server Error:** `GEMINI_API_KEY` is not configured in the server environment.
  - **HTTP 502 Bad Gateway:** Upstream Gemini API error or quota limitation (sanitized to protect secrets).

---

## Project Roadmap & Phase Comparison

| Capability | Phase 1 (Foundation) | Phase 2 (Current) | Future Phases |
| :--- | :--- | :--- | :--- |
| **Web UI** | Responsive layout, dark theme, chat bubbles | Updated with Phase 2 badges & messages | Code highlighting & file tree |
| **Backend Server** | FastAPI with static files & routes | FastAPI + `google-genai` SDK | Streaming (SSE/WebSockets) |
| **AI Integration** | Temporary echo stub | **Live Google Gemini Model** | Agentic tool calling & multi-turn memory |
| **Workspace Tools** | None | **None (Phase boundary)** | File inspection, editing & command execution |
| **Agent Loop** | None | **None (Phase boundary)** | Autonomous multi-step coding agent loop |

---

## Security & Best Practices

- **Zero Secret Leakage:** The API key is read solely by the backend via environment variables. It is never exposed in frontend code, responses, logs, or repository files.
- **XSS Prevention:** All user messages and AI responses are safely injected into the DOM using `textContent`.
- **Error Redaction:** Provider errors are stripped of sensitive values before returning error details.
- **Single-Origin:** The frontend assets and backend API share the same FastAPI instance, eliminating CORS complexity.
