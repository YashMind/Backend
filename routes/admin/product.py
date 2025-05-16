from fastapi import APIRouter, BackgroundTasks, HTTPException,Depends,Body
from sqlalchemy.orm import Session
from config import get_db
from sqlalchemy.exc import SQLAlchemyError
from models.adminModel.productModel import Product ,ProductStatusUpdate
from pydantic import BaseModel

router = APIRouter()
@router.get("/products")


async def get_all_products(db: Session = Depends(get_db)):
    try:
        products = db.query(Product).all()

        formatted_products = [
            {
                "id": product.id,
                "name": product.name,
                "status": product.status,
            }
            for product in products
        ]

        return {
            "success": True,
            "message": "Products fetched successfully.",
            "data": formatted_products
        }
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Something went wrong: {str(e)}")


@router.put("/products/{product_id}/status")
async def update_product_status(
    product_id: int,
    status_update: ProductStatusUpdate = Body(...),
    db: Session = Depends(get_db)
):
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        product.status = status_update.status
        db.commit()
        db.refresh(product)

        return {
            "success": True,
            "message": f"Product status updated to {product.status}",
            "data": {
                "id": product.id,
                "name": product.name,
                "status": product.status,
            },
        }
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Something went wrong: {str(e)}")