from pydantic import BaseModel
from datetime import datetime

class SlackInstallationCreate(BaseModel):
    bot_id: str
    team_id: str
    team_name: str
    bot_user_id: str
    authed_user_id: str
    access_token: str
    installed_at: datetime
