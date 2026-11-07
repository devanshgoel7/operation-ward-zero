"""Best-effort hints for one application worker; REST remains authoritative."""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

EventType = Literal["patient.updated", "alert.updated", "system.status", "heartbeat"]


def message(kind: EventType, **fields: object) -> dict:
    return {"type": kind, "server_time": datetime.now(UTC).isoformat(),
            **{key: str(value) if isinstance(value, UUID) else value
               for key, value in fields.items() if value is not None}}


@dataclass(eq=False)
class Subscriber:
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=32))
    overflow: asyncio.Event = field(default_factory=asyncio.Event)


class RealtimeHub:
    def __init__(self) -> None:
        self.clients: set[Subscriber] = set()

    def subscribe(self) -> Subscriber:
        client = Subscriber()
        self.clients.add(client)
        return client

    def unsubscribe(self, client: Subscriber) -> None:
        self.clients.discard(client)

    def publish(self, kind: EventType, **fields: object) -> None:
        # Never await sockets here: notification delivery cannot delay a commit receipt.
        event = message(kind, **fields)
        for client in tuple(self.clients):
            try:
                client.queue.put_nowait(event)
            except asyncio.QueueFull:
                self.unsubscribe(client)
                client.overflow.set()


def notify(hub: RealtimeHub | None, kind: EventType, **fields: object) -> None:
    if hub is not None:
        try:
            hub.publish(kind, **fields)
        except Exception:
            # The caller has already committed. Polling/reconnect recovers missed hints.
            logging.exception("Could not publish update hint; REST reconciliation remains available.")
