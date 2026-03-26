"""Simple persisted session/history store for web Q&A conversations."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatSessionStore:
    """Persist user sessions and multi-turn chat history in a local JSON file."""

    def __init__(self, store_path: Path):
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] = {"users": {}}
        self._load()

    def _load(self) -> None:
        if not self.store_path.exists():
            return
        try:
            self._data = json.loads(self.store_path.read_text(encoding="utf-8"))
        except Exception:
            self._data = {"users": {}}

    def _save(self) -> None:
        self.store_path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _get_user(self, user_id: str) -> dict[str, Any]:
        users = self._data.setdefault("users", {})
        return users.setdefault(user_id, {"sessions": {}})

    def create_session(self, user_id: str, title: str | None = None) -> dict[str, Any]:
        user = self._get_user(user_id)
        session_id = uuid4().hex
        now = _now_iso()
        session = {
            "session_id": session_id,
            "title": title or "新对话",
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }
        user["sessions"][session_id] = session
        self._save()
        return {
            "session_id": session_id,
            "title": session["title"],
            "created_at": now,
            "updated_at": now,
        }

    def list_sessions(self, user_id: str) -> list[dict[str, Any]]:
        user = self._get_user(user_id)
        sessions = list(user["sessions"].values())
        sessions.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return [
            {
                "session_id": s["session_id"],
                "title": s.get("title") or "新对话",
                "created_at": s.get("created_at"),
                "updated_at": s.get("updated_at"),
                "turn_count": len(s.get("messages", [])) // 2,
            }
            for s in sessions
        ]

    def get_history(self, user_id: str, session_id: str) -> list[dict[str, Any]]:
        user = self._get_user(user_id)
        session = user["sessions"].get(session_id)
        if not session:
            return []
        return session.get("messages", [])

    def ensure_session(self, user_id: str, session_id: str) -> dict[str, Any]:
        user = self._get_user(user_id)
        if session_id in user["sessions"]:
            return user["sessions"][session_id]
        now = _now_iso()
        session = {
            "session_id": session_id,
            "title": "新对话",
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }
        user["sessions"][session_id] = session
        self._save()
        return session

    def append_turn(
        self,
        user_id: str,
        session_id: str,
        question: str,
        answer: str,
    ) -> None:
        session = self.ensure_session(user_id, session_id)
        now = _now_iso()
        session["updated_at"] = now
        if len(session["messages"]) == 0 and session.get("title") == "新对话":
            session["title"] = question[:24] or "新对话"
        session["messages"].append({"role": "user", "content": question, "created_at": now})
        session["messages"].append(
            {"role": "assistant", "content": answer, "created_at": _now_iso()}
        )
        self._save()

