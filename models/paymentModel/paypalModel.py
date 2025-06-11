from pydantic import BaseModel
from typing import Optional

class Item(BaseModel):
    name: str
    description: Optional[str] = None
    quantity: str
    price: str
    currency: str

class OrderRequest(BaseModel):
    items: list[Item]
    return_url: str
    cancel_url: str