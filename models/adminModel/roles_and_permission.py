from sqlalchemy import Column, Integer, String
from sqlalchemy.dialects.mysql import JSON
from config import Base

class RolePermission(Base):
    __tablename__ = "roles_and_permissions"

    id = Column(Integer, primary_key=True, index=True)
    role = Column(String(100), nullable=False, unique=True)
    permissions = Column(JSON, nullable=True)
