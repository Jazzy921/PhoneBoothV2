from collections import defaultdict
from typing import Any
from uuid import UUID

from fastapi import WebSocket


class GatewayManager:
    def __init__(self) -> None:
        self.connections_by_channel: dict[UUID, set[WebSocket]] = defaultdict(set)

    async def subscribe(self, channel_id: UUID, websocket: WebSocket) -> None:
        self.connections_by_channel[channel_id].add(websocket)

    async def unsubscribe(self, channel_id: UUID, websocket: WebSocket) -> None:
        if channel_id in self.connections_by_channel:
            self.connections_by_channel[channel_id].discard(websocket)
            if not self.connections_by_channel[channel_id]:
                del self.connections_by_channel[channel_id]

    async def broadcast(self, channel_id: UUID, event_type: str, data: dict[str, Any]) -> None:
        payload = {"t": event_type, "d": data}
        dead_connections: list[WebSocket] = []

        for websocket in self.connections_by_channel.get(channel_id, set()):
            try:
                await websocket.send_json(payload)
            except Exception:  # noqa: BLE001
                dead_connections.append(websocket)

        for websocket in dead_connections:
            self.connections_by_channel[channel_id].discard(websocket)


manager = GatewayManager()
