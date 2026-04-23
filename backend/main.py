from __future__ import annotations

import json
import mimetypes
import shutil
import uuid
from pathlib import Path
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from . import db, prompts, scoring
from .llm import Attachment, Msg, available_providers, get_client
from .schemas import MessageCreate, SessionCreate

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = BASE_DIR / "data" / "uploads"
FRONTEND_DIR = BASE_DIR / "frontend"

ALLOWED_MIMES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}

app = FastAPI(title="Threepio")


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/api/providers")
def providers_endpoint():
    return {"providers": available_providers()}


@app.post("/api/sessions")
def create_session_endpoint(payload: SessionCreate):
    from .llm import DEFAULT_MODELS, ENV_KEYS
    import os

    if not os.environ.get(ENV_KEYS[payload.llm_provider]):
        raise HTTPException(
            status_code=400,
            detail=f"{payload.llm_provider} API key is not configured",
        )
    sid = db.create_session(
        title=payload.title,
        topic=payload.topic,
        situation=payload.situation,
        user_role=payload.user_role,
        model_role=payload.model_role,
        llm_provider=payload.llm_provider,
        llm_model=DEFAULT_MODELS[payload.llm_provider],
    )
    return {"session_id": sid}


@app.post("/api/sessions/{session_id}/attachments")
async def upload_attachments(session_id: int, files: list[UploadFile]):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "session not found")
    if session["ended_at"]:
        raise HTTPException(400, "session already ended")

    session_dir = UPLOADS_DIR / str(session_id)
    session_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for upload in files:
        mime = upload.content_type or mimetypes.guess_type(upload.filename or "")[0]
        if mime not in ALLOWED_MIMES:
            raise HTTPException(400, f"Unsupported file type: {mime}")
        safe_name = f"{uuid.uuid4().hex}_{Path(upload.filename or 'file').name}"
        dest = session_dir / safe_name
        with dest.open("wb") as f:
            shutil.copyfileobj(upload.file, f)
        att_id = db.add_attachment(
            session_id=session_id,
            filename=upload.filename or safe_name,
            mime_type=mime,
            path=str(dest),
        )
        saved.append({
            "id": att_id,
            "filename": upload.filename or safe_name,
            "mime_type": mime,
        })
    return {"attachments": saved}


def _load_history(session_id: int) -> list[Msg]:
    rows = db.list_messages(session_id)
    return [Msg(role=r["role"], content=r["content"]) for r in rows]


def _load_attachments(session_id: int) -> list[Attachment]:
    rows = db.list_attachments(session_id)
    return [
        Attachment(path=r["path"], filename=r["filename"], mime_type=r["mime_type"])
        for r in rows
    ]


async def _stream_assistant(
    session_id: int, session: dict, opening: bool
) -> AsyncIterator[bytes]:
    system = prompts.build_system_prompt(
        topic=session["topic"],
        situation=session["situation"],
        user_role=session["user_role"],
        model_role=session["model_role"],
    )
    history = _load_history(session_id)
    if opening:
        # First assistant turn: inject the opening-trigger user message.
        history.append(Msg(role="user", content=prompts.OPENING_TRIGGER))

    attachments = _load_attachments(session_id)
    client = get_client(session["llm_provider"], session["llm_model"])

    full: list[str] = []
    try:
        async for delta in client.stream_reply(system, history, attachments):
            full.append(delta)
            yield f"data: {json.dumps({'delta': delta})}\n\n".encode()
    except Exception as exc:
        yield f"data: {json.dumps({'error': str(exc)})}\n\n".encode()
        return

    assistant_text = "".join(full).strip()
    if assistant_text:
        db.add_message(session_id, "assistant", assistant_text)
    yield f"data: {json.dumps({'done': True, 'content': assistant_text})}\n\n".encode()


@app.post("/api/sessions/{session_id}/start")
async def start_session(session_id: int):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "session not found")
    if session["ended_at"]:
        raise HTTPException(400, "session already ended")
    if db.list_messages(session_id):
        raise HTTPException(400, "session already started")

    return StreamingResponse(
        _stream_assistant(session_id, session, opening=True),
        media_type="text/event-stream",
    )


@app.post("/api/sessions/{session_id}/messages")
async def post_message(session_id: int, payload: MessageCreate):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "session not found")
    if session["ended_at"]:
        raise HTTPException(400, "session already ended")

    db.add_message(session_id, "user", payload.content, source=payload.source)
    return StreamingResponse(
        _stream_assistant(session_id, session, opening=False),
        media_type="text/event-stream",
    )


@app.post("/api/sessions/{session_id}/end")
async def end_session(session_id: int):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "session not found")
    if session["ended_at"]:
        return {"feedback": json.loads(session["feedback_json"] or "null")}

    msgs = db.list_messages(session_id)
    user_utterances = [m["content"] for m in msgs if m["role"] == "user"]

    if not user_utterances:
        feedback = {
            "scores": {"quality": 0, "fluency": 0, "communication": 0, "overall": 0},
            "summary": "사용자 발화가 없어 평가할 수 없습니다.",
            "corrections": [],
        }
    else:
        feedback = await scoring.generate_feedback(
            provider=session["llm_provider"],
            model=session["llm_model"],
            user_utterances=user_utterances,
        )

    db.end_session(session_id, feedback)
    return {"feedback": feedback}


@app.get("/api/sessions")
def list_sessions_endpoint():
    return {"sessions": db.list_sessions()}


@app.get("/api/sessions/{session_id}")
def session_detail(session_id: int):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "session not found")
    feedback = json.loads(session["feedback_json"]) if session["feedback_json"] else None
    return {
        "session": {**session, "feedback": feedback, "feedback_json": None},
        "messages": db.list_messages(session_id),
        "attachments": [
            {k: v for k, v in a.items() if k != "path"}
            for a in db.list_attachments(session_id)
        ],
    }


# --- static frontend ---
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(FRONTEND_DIR / "index.html")
