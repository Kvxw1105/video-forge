from pydantic import BaseModel

class Template(BaseModel):
    id: str
    name: str
    type: str = "workflow"
    version: str = "0.1"
    canvas: dict
    segments: list[dict]
    audio: dict
    overlays: dict
