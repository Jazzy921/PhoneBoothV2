from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class UserOut(BaseModel):
    id: UUID
    username: str
    avatar_url: str | None
    created_at: datetime


class PaginationParams(BaseModel):
    limit: int = 50
    before: datetime | None = None
