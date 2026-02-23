from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Message


async def create_message(db: AsyncSession, channel_id: UUID, author_id: UUID, content: str) -> Message:
    message = Message(channel_id=channel_id, author_id=author_id, content=content)
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def edit_message(db: AsyncSession, message: Message, content: str) -> Message:
    message.content = content
    message.edited_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(message)
    return message


async def list_messages(
    db: AsyncSession,
    channel_id: UUID,
    limit: int,
    before: datetime | None,
) -> list[Message]:
    stmt = select(Message).where(Message.channel_id == channel_id).order_by(Message.created_at.desc()).limit(limit)
    if before:
        stmt = stmt.where(Message.created_at < before)
    return (await db.execute(stmt)).scalars().all()
