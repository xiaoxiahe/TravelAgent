"""SQLite 会话与状态持久化。"""
from __future__ import annotations

import dataclasses
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from travel_agent.agent.state import AgentState, Message, Stages
from travel_agent.models.user_profile import UserProfile


BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = BASE_DIR / "data" / "chat_sessions.db"


class ChatSessionStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    current_stage INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    options_json TEXT,
                    is_question INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES chat_sessions(session_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS conversation_state_snapshots (
                    session_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES chat_sessions(session_id) ON DELETE CASCADE
                );
                """
            )

    def create_session(self, title: str = "新的旅行规划") -> str:
        session_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO chat_sessions(session_id, title, current_stage, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, title, Stages.WELCOME, now, now),
            )
        return session_id

    def save_state(self, session_id: str, state: AgentState) -> None:
        now = datetime.utcnow().isoformat()
        title = self._derive_title(state)
        payload = json.dumps(self._serialize_state(state), ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_sessions(session_id, title, current_stage, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    title=excluded.title,
                    current_stage=excluded.current_stage,
                    updated_at=excluded.updated_at
                """,
                (session_id, title, state.get("current_stage", Stages.WELCOME), now, now),
            )
            conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
            for message in state.get("messages", []):
                conn.execute(
                    """
                    INSERT INTO chat_messages(session_id, role, content, options_json, is_question, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        message.role,
                        message.content,
                        json.dumps(message.options, ensure_ascii=False) if message.options else None,
                        1 if message.is_question else 0,
                        now,
                    ),
                )
            conn.execute(
                """
                INSERT INTO conversation_state_snapshots(session_id, state_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    state_json=excluded.state_json,
                    updated_at=excluded.updated_at
                """,
                (session_id, payload, now),
            )

    def list_sessions(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT s.session_id, s.title, s.current_stage, s.updated_at, s.created_at,
                       COUNT(m.id) AS message_count
                FROM chat_sessions s
                LEFT JOIN chat_messages m ON m.session_id = s.session_id
                GROUP BY s.session_id
                ORDER BY s.updated_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def load_state(self, session_id: str) -> AgentState | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT state_json FROM conversation_state_snapshots WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        payload = json.loads(row["state_json"])
        return self._deserialize_state(payload)

    def delete_session(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM conversation_state_snapshots WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))

    def get_session_detail(self, session_id: str) -> dict | None:
        state = self.load_state(session_id)
        if state is None:
            return None
        return {
            "session_id": session_id,
            "state": self._serialize_state(state),
            "messages": [message.model_dump() for message in state.get("messages", [])],
            "current_stage": state.get("current_stage", Stages.WELCOME),
            "trip_plan": state.get("trip_plan"),
        }

    @staticmethod
    def _derive_title(state: AgentState) -> str:
        profile = state.get("user_profile")
        if profile and profile.destination:
            return f"{profile.destination} 行程规划"
        first_user_message = next((msg.content for msg in state.get("messages", []) if msg.role == "user"), "新的旅行规划")
        return first_user_message[:30]

    @staticmethod
    def _serialize_state(state: AgentState) -> dict:
        return {
            "messages": [message.model_dump() for message in state.get("messages", [])],
            "user_profile": state.get("user_profile").model_dump() if state.get("user_profile") else None,
            "current_stage": state.get("current_stage", Stages.WELCOME),
            "answers": ChatSessionStore._make_json_safe(state.get("answers", {})),
            "info_sufficient": state.get("info_sufficient", False),
            "retrieved_docs": ChatSessionStore._make_json_safe(state.get("retrieved_docs", [])),
            "trip_plan": ChatSessionStore._make_json_safe(state.get("trip_plan")),
            "error": state.get("error"),
            "feedback_status": state.get("feedback_status"),
            "revision_target": state.get("revision_target"),
            "question_count": state.get("question_count", 0),
        }

    @staticmethod
    def _make_json_safe(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, list):
            return [ChatSessionStore._make_json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [ChatSessionStore._make_json_safe(item) for item in value]
        if isinstance(value, dict):
            return {
                str(key): ChatSessionStore._make_json_safe(item)
                for key, item in value.items()
            }
        if hasattr(value, "model_dump"):
            return ChatSessionStore._make_json_safe(value.model_dump())
        if dataclasses.is_dataclass(value):
            return ChatSessionStore._make_json_safe(dataclasses.asdict(value))
        if hasattr(value, "__dict__"):
            return ChatSessionStore._make_json_safe(vars(value))
        return str(value)

    @staticmethod
    def _deserialize_state(payload: dict) -> AgentState:
        messages = [Message(**message) for message in payload.get("messages", [])]
        user_profile = payload.get("user_profile")
        return AgentState(
            messages=messages,
            user_profile=UserProfile(**user_profile) if user_profile else None,
            current_stage=payload.get("current_stage", Stages.WELCOME),
            answers=payload.get("answers", {}),
            info_sufficient=payload.get("info_sufficient", False),
            retrieved_docs=payload.get("retrieved_docs", []),
            trip_plan=payload.get("trip_plan"),
            error=payload.get("error"),
            feedback_status=payload.get("feedback_status"),
            revision_target=payload.get("revision_target"),
            question_count=payload.get("question_count", 0),
        )
