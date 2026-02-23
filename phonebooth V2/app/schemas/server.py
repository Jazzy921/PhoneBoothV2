from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateServerIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)


class ServerOut(BaseModel):
    id: UUID
    name: str
    owner_id: UUID
    created_at: datetime


class ServerMemberOut(BaseModel):
    user_id: UUID
    role: str
    joined_at: datetime
