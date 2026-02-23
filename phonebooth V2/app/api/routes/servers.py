from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_server_member, require_server_owner
from app.db.session import get_db
from app.models import Server, ServerMember, User
from app.models.enums import MemberRole
from app.schemas.server import CreateServerIn, ServerOut

router = APIRouter(prefix="/servers", tags=["servers"])


@router.post("", response_model=ServerOut, status_code=status.HTTP_201_CREATED)
async def create_server(
    payload: CreateServerIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ServerOut:
    server = Server(name=payload.name, owner_id=current_user.id)
    db.add(server)
    await db.flush()

    membership = ServerMember(server_id=server.id, user_id=current_user.id, role=MemberRole.OWNER.value)
    db.add(membership)

    await db.commit()
    await db.refresh(server)
    return ServerOut.model_validate(server, from_attributes=True)


@router.get("", response_model=list[ServerOut])
async def list_servers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ServerOut]:
    stmt = (
        select(Server)
        .join(ServerMember, ServerMember.server_id == Server.id)
        .where(ServerMember.user_id == current_user.id)
        .order_by(Server.created_at.desc())
    )
    servers = (await db.execute(stmt)).scalars().all()
    return [ServerOut.model_validate(server, from_attributes=True) for server in servers]


@router.get("/{server_id}", response_model=ServerOut)
async def get_server(
    server_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ServerOut:
    await require_server_member(db, server_id, current_user.id)
    server = (await db.execute(select(Server).where(Server.id == server_id))).scalar_one_or_none()
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")
    return ServerOut.model_validate(server, from_attributes=True)


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(
    server_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    server = await require_server_owner(db, server_id, current_user.id)
    await db.delete(server)
    await db.commit()
