from pydantic import BaseModel
from typing import Optional

class VolumeDiscountSchema(BaseModel):
    id: Optional[int]
    min_tokens: int
    discount_percent: float

    class Config:
        orm_mode = True
