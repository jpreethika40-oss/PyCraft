# PyCraft: My Personal AI Coding Agent

> **Phase 1: Project Foundation & Chat Interface**

PyCraft is an AI coding agent designed to run in a browser-based chat interface backed by Python. When fully realized, PyCraft will inspect and edit project files within a workspace to help developers write, debug, and understand code.

**Phase 1** establishes the clean project architecture, a responsive web chat UI, and a FastAPI backend with message validation and temporary response stubs.

---

## Architecture & Technology Choices

- **Language:** Python 3.10+
- **Backend Framework:** [FastAPI](https://fastapi.tiangolo.com/) for high performance, automatic request validation, and lightweight routing.
- **ASGI Server:** [Uvicorn](https://www.uvicorn.org/) to run the FastAPI application.
- **Frontend:** Vanilla HTML5, CSS3, and modern JavaScript (no heavy frontend frameworks or build steps required).
- **Communication:** HTTP JSON endpoints (`GET /` to serve UI, `POST /chat` to process messages).

---

## Project Structure

```text
PyCraft/
├── app/
│   ├── __init__.py           # Package marker for the app module
│   ├── main.py               # FastAPI routes, input validation & temporary response logic
│   └── static/
│       ├── index.html        # Clean, responsive chat interface
│       ├── styles.css        # Modern responsive dark/light styles
│       └── app.js            # Client-side chat logic, safe DOM rendering & error handling
├── .gitignore                # Ignores venv, caches, local configs & OS files
├── requirements.txt          # Minimal Python dependencies (FastAPI, Uvicorn)
└── README.md                 # Project documentation and run guide
```

---

## Getting Started

### 1. Prerequisites
- Python 3.10 or higher installed on your machine.

### 2. Create and Activate a Virtual Environment

Open your terminal in the `PyCraft` project directory:

**On Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

*(Note: If PowerShell restricts scripts, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first, or activate via CMD).*

**On Windows (Command Prompt):**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

**On macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

Install the minimal required packages:
```bash
pip install -r requirements.txt
```

### 4. Run the Development Server

Start the application with Uvicorn:
```bash
uvicorn app.main:app --reload
```

Or using the Python module syntax:
```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 5. Open in Your Browser

Navigate to:
```
http://127.0.0.1:8000
```

You will see the PyCraft chat interface with its introductory message.

---

## API Endpoints

### 1. `GET /`
- **Purpose:** Serves the PyCraft chat web application (`index.html`).
- **Response:** HTML web page.

### 2. `POST /chat`
- **Purpose:** Receives user chat messages, validates input, and returns a response.
- **Request Body (JSON):**
  ```json
  {
    "message": "Hello PyCraft!"
  }
  ```
- **Response Body (JSON - Status 200 OK):**
  ```json
  {
    "reply": "[PyCraft Phase 1 Temporary Reply] Received: \"Hello PyCraft!\". The AI model is not connected yet and will be added in a later phase.",
    "status": "ok"
  }
  ```
- **Validation Errors:**
  - **HTTP 400 Bad Request:** Returned if the `message` string is empty or contains only whitespace.
    ```json
    { "detail": "Message cannot be empty. Please type a message before sending." }
    ```
  - **HTTP 422 Unprocessable Entity:** Returned if the JSON body is malformed or missing the `message` field.
    ```json
    { "detail": "Invalid request payload. A valid 'message' string is required." }
    ```

---

## Phase 1 Capabilities & Future Roadmap

| Feature | Phase 1 (Current) | Future Phases |
| :--- | :--- | :--- |
| **Chat Web UI** | Fully responsive, safe DOM rendering, visible loading & error states | Code syntax highlighting, workspace file tree, diff viewer |
| **Backend Server** | FastAPI with static file hosting and `/chat` endpoint | Streaming responses (WebSockets/SSE), multi-turn session state |
| **Chat Logic** | Temporary stub acknowledging message receipt | Real AI Model integration (Gemini / Claude / OpenAI) |
| **Tools & Agent Loop** | None (Phase 1 boundary) | File read/write/edit tools, command runner, ReAct reasoning loop |

---

## Security & Best Practices in Phase 1

- **XSS Prevention:** All user-provided text is inserted into the chat DOM via `textContent` rather than `innerHTML`, preventing script injection.
- **Server Input Sanitization:** Messages are stripped and validated on both the client side and the server side.
- **Single-Origin Deployment:** The frontend assets and backend API are hosted from the same FastAPI instance, eliminating unnecessary cross-origin resource sharing (CORS) complexities.
