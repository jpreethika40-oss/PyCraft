import asyncio
import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field

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

# Model configuration: default to gemini-3.5-flash-lite, with safe fallbacks
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
FALLBACK_MODELS = ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.1-flash-lite"]

app = FastAPI(
    title="PyCraft",
    description="Your Personal AI Coding Agent - Backend Server",
    version="0.2.0",
)

# Mount the static directory for CSS, JavaScript, and assets
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class MessageItem(BaseModel):
    role: str = Field(..., description="Message sender role: 'user' or 'model'")
    content: str = Field(..., description="Message text content")


class ChatRequest(BaseModel):
    message: str = Field(..., description="Latest message string sent by the user")
    history: list[MessageItem] = Field(default_factory=list, description="Prior conversation history")


class ChatResponse(BaseModel):
    reply: str = Field(..., description="Reply from PyCraft")
    status: str = Field(default="ok", description="Status indicator")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Provide a clean, readable error message for malformed JSON or missing fields."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Invalid request payload. A valid 'message' string is required."},
    )


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


@app.post("/chat", response_model=ChatResponse, summary="Receive chat message and return Gemini AI reply")
async def chat_endpoint(payload: ChatRequest):
    """
    Handle incoming chat messages and forward them to Google Gemini with conversation context.

    Features:
    - Validates message is non-empty.
    - Dynamically reads GEMINI_API_KEY from environment or .env file.
    - Passes prior session history to support contextual follow-ups.
    - Supports all programming languages and general knowledge questions.
    - Handles model fallbacks, rate limits, and timeouts with clear, safe error messages.
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
    # Take up to the last 20 conversation turns to preserve context without excessive tokens
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

    # 4. Model candidates and configuration
    configured_model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip()
    models_to_try = [configured_model] + [m for m in FALLBACK_MODELS if m != configured_model]

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=60000),  # 60,000 ms = 60 seconds
    )

    config = types.GenerateContentConfig(
        system_instruction=(
            "You are PyCraft, a helpful, intelligent AI assistant. "
            "You answer general questions, reasoning queries, and coding requests across all programming languages "
            "(including Python, Java, C, C++, JavaScript, TypeScript, HTML, CSS, SQL, Go, Rust, and more). "
            "Provide accurate, clear explanations and well-structured code formatted in markdown code blocks."
        )
    )

    last_error_detail = None
    last_status_code = status.HTTP_502_BAD_GATEWAY

    for model_name in models_to_try:
        try:
            logger.info(f"Generating content using model: {model_name}")
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model_name,
                contents=contents,
                config=config,
            )

            if response and response.text:
                return ChatResponse(reply=response.text.strip(), status="ok")
            elif response and response.candidates and response.candidates[0].content:
                parts_text = "".join(p.text for p in response.candidates[0].content.parts if p.text)
                if parts_text.strip():
                    return ChatResponse(reply=parts_text.strip(), status="ok")

            return ChatResponse(
                reply="The model returned an empty response. Please try rephrasing your message.",
                status="ok",
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
            elif "404" in err_msg if "err_msg" in locals() else ("404" in err_text or "NOT_FOUND" in err_text):
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
