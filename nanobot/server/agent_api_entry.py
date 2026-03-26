"""Sanic entrypoint for front-end Q&A calls."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any
from uuid import uuid4

from sanic import Sanic
from sanic import response as sanic_response

from nanobot import __logo__
from nanobot.cli.commands import AgentService

app = Sanic("nanobot-agent-api")
app.config.REQUEST_MAX_SIZE = 20 * 1024 * 1024

_FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"


@app.middleware("response")
async def add_cors_headers(_request, resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Credentials"] = "true"


@app.middleware("request")
async def handle_options_request(request):
    if request.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Allow-Credentials": "true",
        }
        return sanic_response.text("", headers=headers)
    return None


async def health(_request):
    return sanic_response.json({"ok": True, "service": "nanobot-agent-api"})


async def query_agent(request):
    payload: dict[str, Any] = request.json or {}
    user_id = (payload.get("user_id") or "").strip() or "anonymous"
    message = (payload.get("message") or "").strip()
    session_id = (payload.get("session_id") or "").strip()
    if not message:
        return sanic_response.json(
            {"success": False, "error": "`message` is required"},
            status=400,
        )
    created_session = False
    if not session_id:
        session = _create_web_session(user_id=user_id)
        session_id = session["session_id"]
        created_session = True
    else:
        _get_or_create_web_session(user_id=user_id, session_id=session_id)

    try:
        runtime_session_id = f"web:{user_id}:{session_id}"
        answer = await app.ctx.agent_service.ask(
            message=message,
            session_id=runtime_session_id,
        )
    except Exception as exc:
        return sanic_response.json({"success": False, "error": str(exc)}, status=500)

    return sanic_response.json(
        {
            "success": True,
            "user_id": user_id,
            "session_id": session_id,
            "created_session": created_session,
            "message": message,
            "response": answer,
        }
    )


async def create_session(request):
    payload: dict[str, Any] = request.json or {}
    user_id = (payload.get("user_id") or "").strip() or "anonymous"
    title = (payload.get("title") or "").strip() or None
    session = _create_web_session(user_id=user_id, title=title)
    return sanic_response.json({"success": True, "user_id": user_id, "session": session})


async def list_sessions(request):
    user_id = (request.args.get("user_id") or "").strip() or "anonymous"
    sessions = _list_web_sessions(user_id=user_id)
    return sanic_response.json({"success": True, "user_id": user_id, "sessions": sessions})


async def session_history(request):
    user_id = (request.args.get("user_id") or "").strip() or "anonymous"
    session_id = (request.args.get("session_id") or "").strip()
    if not session_id:
        return sanic_response.json(
            {"success": False, "error": "`session_id` is required"},
            status=400,
        )
    history = _get_web_history(user_id=user_id, session_id=session_id)
    return sanic_response.json(
        {
            "success": True,
            "user_id": user_id,
            "session_id": session_id,
            "messages": history,
        }
    )


@app.before_server_start
async def init_agent_service(_app, _loop):
    app.ctx.agent_service = AgentService.from_runtime_options(
        config_path=app.ctx.config_path,
        workspace=app.ctx.workspace,
        logs=app.ctx.logs,
    )
    app.ctx.session_manager = app.ctx.agent_service.runtime_api.loop.sessions


@app.after_server_stop
async def close_agent_service(_app, _loop):
    if getattr(app.ctx, "agent_service", None) is not None:
        await app.ctx.agent_service.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8777, help="Bind port")
    parser.add_argument("--workers", type=int, default=1, help="Sanic worker count")
    parser.add_argument("--workspace", type=str, default=None, help="Workspace directory override")
    parser.add_argument("--config", type=str, default=None, help="Config file path")
    parser.add_argument("--logs", action="store_true", help="Enable runtime logs")
    args = parser.parse_args()

    app.ctx.workspace = args.workspace
    app.ctx.config_path = args.config
    app.ctx.logs = args.logs

    app.add_route(health, "/api/agent/health", methods=["GET"])
    app.add_route(query_agent, "/api/agent/query", methods=["POST"])
    app.add_route(create_session, "/api/agent/session/new", methods=["POST"])
    app.add_route(list_sessions, "/api/agent/session/list", methods=["GET"])
    app.add_route(session_history, "/api/agent/session/history", methods=["GET"])

    if _FRONTEND_DIR.exists():
        app.static("/", str(_FRONTEND_DIR), index="index.html", name="frontend")

    print(f"{__logo__} Starting Sanic agent API at http://{args.host}:{args.port}")
    print("Frontend page: /")
    print("POST /api/agent/query with JSON {\"user_id\": \"u1\", \"session_id\": \"...\", \"message\": \"...\"}")
    app.run(
        host=args.host,
        port=args.port,
        workers=args.workers,
        access_log=args.logs,
        single_process=args.workers == 1,
    )


if __name__ == "__main__":
    main()


def _session_key(user_id: str, session_id: str) -> str:
    return f"web:{user_id}:{session_id}"


def _get_or_create_web_session(user_id: str, session_id: str):
    manager = app.ctx.session_manager
    key = _session_key(user_id, session_id)
    session = manager.get_or_create(key)
    return session


def _create_web_session(user_id: str, title: str | None = None) -> dict[str, Any]:
    manager = app.ctx.session_manager
    session_id = uuid4().hex
    key = _session_key(user_id, session_id)
    session = manager.get_or_create(key)
    session.metadata["title"] = title or "新对话"
    manager.save(session)
    return {
        "session_id": session_id,
        "title": session.metadata.get("title", "新对话"),
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }


def _list_web_sessions(user_id: str) -> list[dict[str, Any]]:
    manager = app.ctx.session_manager
    prefix = f"web:{user_id}:"
    sessions = []
    for row in manager.list_sessions():
        key = row.get("key", "")
        if not key.startswith(prefix):
            continue
        session_id = key[len(prefix):]
        session = manager.get_or_create(key)
        sessions.append(
            {
                "session_id": session_id,
                "title": session.metadata.get("title") or "新对话",
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
                "turn_count": len([m for m in session.messages if m.get("role") == "user"]),
            }
        )
    sessions.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return sessions


def _get_web_history(user_id: str, session_id: str) -> list[dict[str, Any]]:
    session = _get_or_create_web_session(user_id, session_id)
    history = []
    for m in session.messages:
        role = m.get("role")
        if role not in {"user", "assistant"}:
            continue
        content = m.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        history.append(
            {
                "role": role,
                "content": content,
                "created_at": m.get("timestamp"),
            }
        )
    return history
