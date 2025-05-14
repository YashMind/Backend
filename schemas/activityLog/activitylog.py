from pydantic import BaseModel
from datetime import datetime

class ActivityLogSchema(BaseModel):
    id: int
    user_id: int
    username: str
    role: str
    action: str
    log_activity: str
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
