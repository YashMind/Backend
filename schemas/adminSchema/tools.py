from pydantic import BaseModel

class Tools(BaseModel):
    id: int
    name: str
    status: str