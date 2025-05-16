from sqlalchemy import Column, Integer, String
from config import Base  

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    status = Column(String(50), default="active")
    
class ProductStatusUpdate(BaseModel):
    status: str