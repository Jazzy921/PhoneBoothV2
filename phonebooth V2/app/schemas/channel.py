from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class CreateChannelIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    channel_type: Literal["text", "voice"] = "text"
    position: int = 0


class ChannelOut(BaseModel):
    id: UUID
    server_id: UUID
    name: str
    channel_type: str
    position: int
    created_at: datetime
