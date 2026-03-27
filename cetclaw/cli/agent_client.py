"""Reusable API wrapper for `cetclaw agent` runtime."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from cetclaw.agent.loop import AgentLoop
from cetclaw.bus.queue import MessageBus
from cetclaw.config.paths import get_cron_dir
from cetclaw.config.schema import Config
from cetclaw.cron.service import CronService

ProgressCallback = Callable[[str], Awaitable[None]]


@dataclass(slots=True)
class AgentClient:
    """Encapsulate agent runtime initialization for reusable Q&A integration."""

    loop: AgentLoop
    _ask_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    @classmethod
    def from_config(cls, config: Config, provider) -> "AgentClient":
        """Build an API instance with the same defaults as `cetclaw agent`."""
        bus = MessageBus()
        cron_store_path = get_cron_dir() / "jobs.json"
        cron = CronService(cron_store_path)
        loop = AgentLoop(
            bus=bus,
            provider=provider,
            workspace=config.workspace_path,
            model=config.agents.defaults.model,
            max_iterations=config.agents.defaults.max_tool_iterations,
            context_window_tokens=config.agents.defaults.context_window_tokens,
            web_search_config=config.tools.web.search,
            web_proxy=config.tools.web.proxy or None,
            exec_config=config.tools.exec,
            cron_service=cron,
            restrict_to_workspace=config.tools.restrict_to_workspace,
            mcp_servers=config.tools.mcp_servers,
            channels_config=config.channels,
        )
        return cls(loop=loop)

    async def ask(
        self,
        message: str,
        session_id: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> str:
        """Submit a single-turn question and return agent response text.

        Calls are serialized per runtime instance to avoid shared tool/session context
        interference when multiple callers hit the same API object concurrently.
        """
        if not session_id:
            raise ValueError("session_id is required for API calls; use a unique value like 'channel:user_or_conversation'.")

        if ":" in session_id:
            channel, chat_id = session_id.split(":", 1)
        else:
            channel, chat_id = "cli", session_id

        print(f"session_id: {session_id}")
        async with self._ask_lock:
            return await self.loop.process_direct(
                message,
                session_key=session_id,
                channel=channel,
                chat_id=chat_id,
                on_progress=on_progress,
            )

    async def close(self) -> None:
        """Release MCP and other resources opened by the agent loop."""
        await self.loop.close_mcp()
