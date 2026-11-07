import asyncio
from contextlib import suppress

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.realtime import message

router = APIRouter(prefix="/api/v1")
HEARTBEAT_SECONDS = 10
SEND_TIMEOUT_SECONDS = 3


@router.websocket("/ws")
async def updates(socket: WebSocket) -> None:
    await socket.accept()
    hub = socket.app.state.realtime
    client = hub.subscribe()

    async def send() -> None:
        loop = asyncio.get_running_loop()
        next_heartbeat = loop.time() + HEARTBEAT_SECONDS
        while True:
            remaining = max(0, next_heartbeat - loop.time())
            try:
                event = await asyncio.wait_for(client.queue.get(), timeout=remaining)
            except TimeoutError:
                event = message("heartbeat")
                next_heartbeat = loop.time() + HEARTBEAT_SECONDS
            await asyncio.wait_for(socket.send_json(event), timeout=SEND_TIMEOUT_SECONDS)

    async def receive() -> None:
        while True:
            if (await socket.receive())["type"] == "websocket.disconnect":
                return

    tasks = [asyncio.create_task(send()), asyncio.create_task(receive()),
             asyncio.create_task(client.overflow.wait())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        hub.unsubscribe(client)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        with suppress(WebSocketDisconnect, RuntimeError, OSError, TimeoutError):
            await asyncio.wait_for(socket.close(code=1013 if client.overflow.is_set() else 1000), timeout=1)
