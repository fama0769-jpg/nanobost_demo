"""Message bus module for decoupled channel-agent communication."""

from cetclaw.bus.events import InboundMessage, OutboundMessage
from cetclaw.bus.queue import MessageBus

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
