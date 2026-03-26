"""Sanic entrypoint for front-end Q&A calls."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from sanic import Sanic
from sanic import response as sanic_response

from nanobot import __logo__
from nanobot.cli.commands import AgentService
from nanobot.server.session_store import ChatSessionStore

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
        session = app.ctx.session_store.create_session(user_id=user_id)
        session_id = session["session_id"]
        created_session = True
    else:
        app.ctx.session_store.ensure_session(user_id=user_id, session_id=session_id)

    try:
        runtime_session_id = f"web:{user_id}:{session_id}"
        answer = await app.ctx.agent_service.ask(
            message=message,
            session_id=runtime_session_id,
        )
    except Exception as exc:
        return sanic_response.json({"success": False, "error": str(exc)}, status=500)

    app.ctx.session_store.append_turn(
        user_id=user_id,
        session_id=session_id,
        question=message,
        answer=answer,
    )

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
    session = app.ctx.session_store.create_session(user_id=user_id, title=title)
    return sanic_response.json({"success": True, "user_id": user_id, "session": session})


async def list_sessions(request):
    user_id = (request.args.get("user_id") or "").strip() or "anonymous"
    sessions = app.ctx.session_store.list_sessions(user_id=user_id)
    return sanic_response.json({"success": True, "user_id": user_id, "sessions": sessions})


async def session_history(request):
    user_id = (request.args.get("user_id") or "").strip() or "anonymous"
    session_id = (request.args.get("session_id") or "").strip()
    if not session_id:
        return sanic_response.json(
            {"success": False, "error": "`session_id` is required"},
            status=400,
        )
    history = app.ctx.session_store.get_history(user_id=user_id, session_id=session_id)
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
    app.ctx.session_store = ChatSessionStore(app.ctx.store_path)
    app.ctx.agent_service = AgentService.from_runtime_options(
        config_path=app.ctx.config_path,
        workspace=app.ctx.workspace,
        logs=app.ctx.logs,
    )


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
    parser.add_argument("--session-store", type=str, default=None, help="Session store JSON path")
    args = parser.parse_args()

    app.ctx.workspace = args.workspace
    app.ctx.config_path = args.config
    app.ctx.logs = args.logs
    if args.session_store:
        app.ctx.store_path = Path(args.session_store).expanduser()
    else:
        default_root = Path(args.workspace).expanduser() if args.workspace else Path.home() / ".nanobot"
        app.ctx.store_path = default_root / "sessions" / "chat_sessions.json"

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
