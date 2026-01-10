from pydantic import BaseModel
from typing import Optional


class TV(BaseModel):
    ip: str
    name: str
    model: str
    last_updated: Optional[str]
    mac: str
    token: Optional[str]


class WakeRequest(BaseModel):
    # For unicast WOL we only need a port (default 9)
    port: Optional[int] = 9
