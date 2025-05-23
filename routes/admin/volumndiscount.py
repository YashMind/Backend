from fastapi import APIRouter, BackgroundTasks, HTTPException,Depends,Body
from sqlalchemy.orm import Session
from config import get_db
from sqlalchemy.exc import SQLAlchemyError
from models.adminModel.volumnDiscountModel import VolumeDiscount
from pydantic import BaseModel

router = APIRouter()

class DiscountUpdateSchema(BaseModel):
    discount: float


@router.put("/discounts/{discount_id}")
async def update_discount(discount_id: int, payload: DiscountUpdateSchema, db: Session = Depends(get_db)):
    try:
        discount_record = db.query(VolumeDiscount).filter(VolumeDiscount.id == discount_id).first()

        if not discount_record:
            raise HTTPException(status_code=404, detail="Discount record not found")

        discount_record.discount_percent = payload.discount

        db.commit()
        db.refresh(discount_record)

        return {
            "success": True,
            "message": "Discount updated successfully.",
            "data": {
                "id": discount_record.id,
                "token": discount_record.min_tokens,
                "discount": discount_record.discount_percent
            }
        }
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Something went wrong: {str(e)}")

@router.get("/get-volumn-discounts")
async def get_volumn_discounts(db: Session = Depends(get_db)):
    try:
        discounts = db.query(VolumeDiscount).all()

        formatted_discounts = [
            {
                "id": discount.id,
                "token": discount.min_tokens,
                "discount": discount.discount_percent,
            }
            for discount in discounts
        ]

        return {
            "success": True,
            "message": "Discounts fetched successfully.",
            "data": formatted_discounts
        }
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Something went wrong: {str(e)}")