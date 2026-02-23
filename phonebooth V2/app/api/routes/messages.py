from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_channel_member
from app.db.session import get_db
from app.models import Message, User
from app.schemas.message import CreateMessageIn, MessageOut, UpdateMessageIn
from app.services.message_service import create_message, edit_message, list_messages

router = APIRouter(prefix="/channels/{channel_id}/messages", tags=["messages"])


@router.post("", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def create_message_route(
    channel_id: UUID,
    payload: CreateMessageIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageOut:
    await require_channel_member(db, channel_id, current_user.id)
    message = await create_message(db, channel_id, current_user.id, payload.content)
    return MessageOut.model_validate(message, from_attributes=True)


@router.get("", response_model=list[MessageOut])
async def list_channel_messages(
    channel_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    before: datetime | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MessageOut]:
    await require_channel_member(db, channel_id, current_user.id)
    rows = await list_messages(db, channel_id, limit, before)
    return [MessageOut.model_validate(item, from_attributes=True) for item in rows]


@router.patch("/{message_id}", response_model=MessageOut)
async def update_message_route(
    channel_id: UUID,
    message_id: UUID,
    payload: UpdateMessageIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageOut:
    await require_channel_member(db, channel_id, current_user.id)
    stmt = select(Message).where(Message.id == message_id, Message.channel_id == channel_id)
    message = (await db.execute(stmt)).scalar_one_or_none()
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    if message.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot edit another user's message")

    updated = await edit_message(db, message, payload.content)
    return MessageOut.model_validate(updated, from_attributes=True)


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message_route(
    channel_id: UUID,
    message_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    await require_channel_member(db, channel_id, current_user.id)
    stmt = select(Message).where(Message.id == message_id, Message.channel_id == channel_id)
    message = (await db.execute(stmt)).scalar_one_or_none()
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    if message.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete another user's message")

    await db.delete(message)
    await db.commit()
