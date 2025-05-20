from fastapi import APIRouter, BackgroundTasks, HTTPException,Depends,Body
from sqlalchemy.orm import Session
from config import get_db
from sqlalchemy.exc import SQLAlchemyError
from models.adminModel.volumnDiscountModel import VolumeDiscount
from pydantic import BaseModel

router = APIRouter()
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