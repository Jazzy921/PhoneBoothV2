from typing import Any

from pydantic import BaseModel


class GatewayEventIn(BaseModel):
    op: str
    d: dict[str, Any]


class GatewayEventOut(BaseModel):
    t: str
    d: dict[str, Any]
