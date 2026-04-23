from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  topic TEXT NOT NULL,
  situation TEXT NOT NULL,
  user_role TEXT NOT NULL,
  model_role TEXT NOT NULL,
  llm_provider TEXT NOT NULL,
  llm_model TEXT NOT NULL,
  created_at TEXT NOT NULL,
  ended_at TEXT,
  feedback_json TEXT
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  source TEXT,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attachments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  path TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_attachments_session ON attachments(session_id);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(SCHEMA)


def create_session(
    *,
    title: str,
    topic: str,
    situation: str,
    user_role: str,
    model_role: str,
    llm_provider: str,
    llm_model: str,
) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO sessions
               (title, topic, situation, user_role, model_role,
                llm_provider, llm_model, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, topic, situation, user_role, model_role,
             llm_provider, llm_model, _now_iso()),
        )
        return cur.lastrowid


def get_session(session_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    return dict(row) if row else None


def list_sessions() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT id, title, topic, llm_provider, llm_model,
                      created_at, ended_at
               FROM sessions ORDER BY id DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def end_session(session_id: int, feedback: dict[str, Any] | None) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE sessions SET ended_at = ?, feedback_json = ? WHERE id = ?",
            (_now_iso(), json.dumps(feedback, ensure_ascii=False) if feedback else None, session_id),
        )


def add_message(
    session_id: int, role: str, content: str, source: str | None = None
) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO messages (session_id, role, source, content, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, role, source, content, _now_iso()),
        )
        return cur.lastrowid


def list_messages(session_id: int) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT id, role, source, content, created_at
               FROM messages WHERE session_id = ? ORDER BY id ASC""",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def add_attachment(
    session_id: int, filename: str, mime_type: str, path: str
) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO attachments (session_id, filename, mime_type, path)
               VALUES (?, ?, ?, ?)""",
            (session_id, filename, mime_type, path),
        )
        return cur.lastrowid


def list_attachments(session_id: int) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT id, filename, mime_type, path
               FROM attachments WHERE session_id = ? ORDER BY id ASC""",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]
