import asyncio
from fastapi import WebSocket


class ConnectionManager:
    """In-memory connection manager — channel -> set of live WebSocket connections.
    Fine at this prototype's scale (single backend process); a multi-instance
    deployment would swap this for Redis pub/sub without changing the public API
    below (connect/disconnect/subscribe/unsubscribe/publish)."""

    def __init__(self) -> None:
        self._channel_connections: dict[str, set[WebSocket]] = {}
        self._connection_user: dict[WebSocket, str] = {}
        self._connection_channels: dict[WebSocket, set[str]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: str) -> None:
        await websocket.accept()
        async with self._lock:
            self._connection_user[websocket] = user_id
            self._connection_channels[websocket] = set()
            # Every connection is implicitly subscribed to its own personal channel —
            # the client never has to ask for its own notifications explicitly.
            personal = f"user:{user_id}:notifications"
            self._channel_connections.setdefault(personal, set()).add(websocket)
            self._connection_channels[websocket].add(personal)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            channels = self._connection_channels.pop(websocket, set())
            for ch in channels:
                conns = self._channel_connections.get(ch)
                if conns:
                    conns.discard(websocket)
                    if not conns:
                        del self._channel_connections[ch]
            self._connection_user.pop(websocket, None)

    async def subscribe(self, websocket: WebSocket, channel: str) -> None:
        async with self._lock:
            self._channel_connections.setdefault(channel, set()).add(websocket)
            self._connection_channels.setdefault(websocket, set()).add(channel)

    async def unsubscribe(self, websocket: WebSocket, channel: str) -> None:
        async with self._lock:
            conns = self._channel_connections.get(channel)
            if conns:
                conns.discard(websocket)
                if not conns:
                    del self._channel_connections[channel]
            chans = self._connection_channels.get(websocket)
            if chans:
                chans.discard(channel)

    async def publish(self, channel: str, message: dict) -> int:
        """Broadcasts to every connection subscribed to `channel`. Returns the number
        of connections it was actually sent to, so callers can tell if anyone was
        listening at all."""
        async with self._lock:
            targets = list(self._channel_connections.get(channel, set()))
        sent = 0
        for ws in targets:
            try:
                await ws.send_json(message)
                sent += 1
            except Exception:
                pass  # a dead connection here will be cleaned up by its own disconnect handler
        return sent

    def active_count(self) -> int:
        return len(self._connection_user)


_manager = ConnectionManager()


def get_manager() -> ConnectionManager:
    return _manager
