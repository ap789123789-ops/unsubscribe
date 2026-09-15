from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ready"] = "ready"
    api_version: Literal["v1"] = "v1"
