from typing import Literal

from pydantic import BaseModel


class OllamaStatusResponse(BaseModel):
    status: Literal["connected"] = "connected"
    models: list[str]
