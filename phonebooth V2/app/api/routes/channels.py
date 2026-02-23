from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_server_member, require_server_owner
from app.db.session import get_db
from app.models import Channel, User
from app.schemas.channel import ChannelOut, CreateChannelIn

router = APIRouter(tags=["channels"])


@router.post("/servers/{server_id}/channels", response_model=ChannelOut, status_code=status.HTTP_201_CREATED)
async def create_channel(
    server_id: UUID,
    payload: CreateChannelIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChannelOut:
    await require_server_owner(db, server_id, current_user.id)
    channel = Channel(
        server_id=server_id,
        name=payload.name,
        channel_type=payload.channel_type,
        position=payload.position,
    )
    db.add(channel)
    await db.commit()
    await db.refresh(channel)
    return ChannelOut.model_validate(channel, from_attributes=True)


@router.get("/servers/{server_id}/channels", response_model=list[ChannelOut])
async def list_channels(
    server_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ChannelOut]:
    await require_server_member(db, server_id, current_user.id)
    stmt = select(Channel).where(Channel.server_id == server_id).order_by(Channel.position.asc(), Channel.created_at.asc())
    channels = (await db.execute(stmt)).scalars().all()
    return [ChannelOut.model_validate(channel, from_attributes=True) for channel in channels]


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    channel = (await db.execute(select(Channel).where(Channel.id == channel_id))).scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

    await require_server_owner(db, channel.server_id, current_user.id)
    await db.delete(channel)
    await db.commit()
