# models/adminModel/volumeDiscountModel.py

from sqlalchemy import Column, Integer, Float, DateTime, func
from config import Base

class VolumeDiscount(Base):
    __tablename__ = "volume_discounts"

    id = Column(Integer, primary_key=True, index=True)
    min_tokens = Column(Integer, nullable=False)
    discount_percent = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
