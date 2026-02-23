from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_or_create_user_from_token, require_channel_member
from app.db.session import AsyncSessionLocal
from app.schemas.message import CreateMessageIn, MessageOut
from app.schemas.ws import GatewayEventIn
from app.services.message_service import create_message
from app.websocket.manager import manager

router = APIRouter(tags=["gateway"])


@router.websocket("/gateway")
async def gateway(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401)
        return

    await websocket.accept()

    active_channels: set[UUID] = set()

    try:
        async with AsyncSessionLocal() as db:
            user = await get_or_create_user_from_token(db, token)

            while True:
                raw_event = await websocket.receive_json()

                try:
                    event = GatewayEventIn.model_validate(raw_event)
                except ValidationError:
                    await websocket.send_json({"t": "ERROR", "d": {"message": "Invalid gateway payload"}})
                    continue

                if event.op == "join_channel":
                    try:
                        channel_id = UUID(str(event.d.get("channel_id")))
                    except ValueError:
                        await websocket.send_json({"t": "ERROR", "d": {"message": "Invalid channel_id"}})
                        continue
                    await require_channel_member(db, channel_id, user.id)
                    await manager.subscribe(channel_id, websocket)
                    active_channels.add(channel_id)
                    await websocket.send_json({"t": "CHANNEL_JOINED", "d": {"channel_id": str(channel_id)}})
                    continue

                if event.op == "leave_channel":
                    try:
                        channel_id = UUID(str(event.d.get("channel_id")))
                    except ValueError:
                        await websocket.send_json({"t": "ERROR", "d": {"message": "Invalid channel_id"}})
                        continue
                    if channel_id in active_channels:
                        await manager.unsubscribe(channel_id, websocket)
                        active_channels.discard(channel_id)
                    await websocket.send_json({"t": "CHANNEL_LEFT", "d": {"channel_id": str(channel_id)}})
                    continue

                if event.op == "send_message":
                    try:
                        channel_id = UUID(str(event.d.get("channel_id")))
                    except ValueError:
                        await websocket.send_json({"t": "ERROR", "d": {"message": "Invalid channel_id"}})
                        continue
                    await require_channel_member(db, channel_id, user.id)

                    payload = CreateMessageIn.model_validate({"content": event.d.get("content")})
                    message = await create_message(db, channel_id, user.id, payload.content)
                    data = MessageOut.model_validate(message, from_attributes=True).model_dump(mode="json")

                    await manager.broadcast(channel_id, "MESSAGE_CREATE", data)
                    continue

                await websocket.send_json({"t": "ERROR", "d": {"message": "Unknown opcode"}})
    except WebSocketDisconnect:
        pass
    finally:
        for channel_id in active_channels:
            await manager.unsubscribe(channel_id, websocket)
