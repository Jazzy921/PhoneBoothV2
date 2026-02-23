from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_supabase_jwt
from app.db.session import get_db
from app.models import Channel, Server, ServerMember, User


async def get_or_create_user_from_token(db: AsyncSession, token: str) -> User:
    payload = await verify_supabase_jwt(token)

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    try:
        supabase_user_id = UUID(sub)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user id in token") from exc

    stmt = select(User).where(User.supabase_user_id == supabase_user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()

    if user is None:
        raw_meta = payload.get("user_metadata") or {}
        username = raw_meta.get("username") or raw_meta.get("full_name") or payload.get("email") or f"user-{str(supabase_user_id)[:8]}"
        avatar_url = raw_meta.get("avatar_url")
        user = User(supabase_user_id=supabase_user_id, username=username, avatar_url=avatar_url)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return user


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1]
    return await get_or_create_user_from_token(db, token)


async def require_server_member(db: AsyncSession, server_id: UUID, user_id: UUID) -> ServerMember:
    stmt = select(ServerMember).where(ServerMember.server_id == server_id, ServerMember.user_id == user_id)
    member = (await db.execute(stmt)).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a server member")
    return member


async def require_server_owner(db: AsyncSession, server_id: UUID, user_id: UUID) -> Server:
    stmt = select(Server).where(Server.id == server_id, Server.owner_id == user_id)
    server = (await db.execute(stmt)).scalar_one_or_none()
    if server is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only server owner can perform this action")
    return server


async def require_channel_member(db: AsyncSession, channel_id: UUID, user_id: UUID) -> Channel:
    stmt = (
        select(Channel)
        .join(Server, Server.id == Channel.server_id)
        .join(ServerMember, ServerMember.server_id == Server.id)
        .where(Channel.id == channel_id, ServerMember.user_id == user_id)
    )
    channel = (await db.execute(stmt)).scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to channel")
    return channel
