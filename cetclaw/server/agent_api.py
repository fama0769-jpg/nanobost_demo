"""Sanic entrypoint for front-end Q&A calls."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from sanic import Sanic
from sanic import response as sanic_response

from cetclaw import __logo__
from cetclaw.cli.commands import AgentService
from cetclaw.server.session_store import ChatSessionStore

app = Sanic("cetclaw-agent-api")
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
    return sanic_response.json({"ok": True, "service": "cetclaw-agent-api"})


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
        import traceback
        from loguru import logger

        logger.exception("Query failed: user={}, session={}, error={}",
                         user_id, session_id, exc)

        # Classify error type for better user messaging
        error_msg = str(exc)
        error_msg_lower = error_msg.lower()

        if "timeout" in error_msg_lower or "timed out" in error_msg_lower:
            error_type = "timeout"
            user_msg = "请求超时，请检查网络连接或稍后重试"
        elif "429" in error_msg or "rate limit" in error_msg_lower:
            error_type = "rate_limit"
            user_msg = "请求过于频繁，请稍后重试"
        elif ("api" in error_msg_lower and "key" in error_msg_lower) or "unauthorized" in error_msg_lower or "401" in error_msg:
            error_type = "auth"
            user_msg = "API Key 配置错误，请检查配置文件"
        elif "connection" in error_msg_lower or "network" in error_msg_lower:
            error_type = "network"
            user_msg = "网络连接失败，请检查网络设置"
        else:
            error_type = "unknown"
            user_msg = "问答请求失败，请查看后端日志获取详细信息"

        return sanic_response.json(
            {
                "success": False,
                "error": error_msg,
                "error_type": error_type,
                "user_message": user_msg,
            },
            status=500,
        )

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
        default_root = Path(args.workspace).expanduser() if args.workspace else Path.home() / ".cetclaw"
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
