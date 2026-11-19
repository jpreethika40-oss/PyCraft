from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Base directory paths
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="PyCraft",
    description="Your Personal AI Coding Agent - Backend Server",
    version="0.1.0",
)

# Mount the static directory for CSS, JavaScript, and assets
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class ChatRequest(BaseModel):
    message: str = Field(..., description="Message string sent by the user")


class ChatResponse(BaseModel):
    reply: str = Field(..., description="Reply from PyCraft")
    status: str = Field(default="ok", description="Status code or indicator")


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


@app.post("/chat", response_model=ChatResponse, summary="Receive chat message and return reply")
async def chat_endpoint(payload: ChatRequest):
    """
    Handle incoming chat messages.

    Phase 1 implementation:
    - Validates message is non-empty.
    - Returns a temporary acknowledgment acknowledging receipt.
    - Explicitly states the AI model will be connected in a later phase.
    """
    raw_message = payload.message
    cleaned_message = raw_message.strip()

    if not cleaned_message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message cannot be empty. Please type a message before sending.",
        )

    temporary_reply = (
        f"[PyCraft Phase 1 Temporary Reply] Received: \"{cleaned_message}\". "
        "The AI model will be connected in a later phase."
    )

    return ChatResponse(reply=temporary_reply, status="ok")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
