from fastapi import Depends, HTTPException, APIRouter
from config import get_db
from models.chatModel.appearance import ChatSettings
from schemas.chatSchema.appearanceSchema import ChatSettingsBase,ChatSettingsCreate,ChatSettingsRead,ChatSettingsUpdate

router = APIRouter()

# CRUD operations
class CRUDChatSettings:
    def create(self, db: get_db, obj_in: ChatSettingsCreate) -> ChatSettings:
        db_obj = ChatSettings(**obj_in.dict())
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get(self, db: get_db, bot_id: int) -> ChatSettings:
        return db.query(ChatSettings).filter(ChatSettings.bot_id == bot_id).first()

    def update(self, db: get_db, bot_id: int, obj_in: ChatSettingsUpdate) -> ChatSettings:
        db_obj = db.query(ChatSettings).filter(ChatSettings.bot_id == bot_id).first()
        if not db_obj:
            raise HTTPException(status_code=404, detail="Settings not found")
        
        update_data = obj_in.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_obj, key, value)
            
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: get_db, id: int) -> ChatSettings:
        db_obj = db.query(ChatSettings).filter(ChatSettings.id == id).first()
        if not db_obj:
            raise HTTPException(status_code=404, detail="Settings not found")
        
        db.delete(db_obj)
        db.commit()
        return db_obj

crud = CRUDChatSettings()

@router.post("/settings/", response_model=ChatSettingsRead)
def create_settings(settings: ChatSettingsCreate, db: get_db = Depends(get_db)):
    return crud.create(db, settings)

@router.get("/settings/{bot_id}", response_model=ChatSettingsRead)
def read_settings(bot_id: int, db: get_db = Depends(get_db)):
    settings = crud.get(db, bot_id)
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")
    return settings

@router.put("/settings/{id}", response_model=ChatSettingsRead)
def update_settings(id: int, settings: ChatSettingsUpdate, db: get_db = Depends(get_db)):
    return crud.update(db, id, settings)

@router.delete("/settings/{id}", response_model=ChatSettingsRead)
def delete_settings(id: int, db: get_db = Depends(get_db)):
    return crud.delete(db, id)