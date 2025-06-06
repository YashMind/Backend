from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, Body, Request
from sqlalchemy.orm import Session
from config import get_db
from sqlalchemy.exc import SQLAlchemyError
from decorators.rbac_admin import check_permissions
from models.adminModel.toolsModal import ToolsUsed, ToolStatusUpdate
from pydantic import BaseModel

router = APIRouter()


@router.get("/tools")
@check_permissions(["product-monitoring"])
async def get_all_tools(request: Request, db: Session = Depends(get_db)):
    try:
        tools = db.query(ToolsUsed).all()

        formatted_tools = [
            {
                "id": tool.id,
                "tool": tool.tool,
                "model": tool.model,
                "status": tool.status,
            }
            for tool in tools
        ]

        return {
            "success": True,
            "message": "Tools fetched successfully.",
            "data": formatted_tools,
        }
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Something went wrong: {str(e)}")


@router.put("/tool/{tool_id}/status")
@check_permissions(["product-monitoring"])
async def tool_status(
    request: Request,
    tool_id: int,
    tool_status: ToolStatusUpdate = Body(...),
    db: Session = Depends(get_db),
):
    try:
        tool = db.query(ToolsUsed).filter(ToolsUsed.id == tool_id).first()
        if not tool:
            raise HTTPException(status_code=404, detail="Tool not found")
        db.query(ToolsUsed).update({ToolsUsed.status: 0})
        tool.status = tool_status.status
        db.commit()
        db.refresh(tool)

        return {
            "success": True,
            "message": f"Tool status updated to {tool.status}",
            "data": {
                "id": tool.id,
                "name": tool.tool,
                "model": tool.model,
                "status": tool.status,
            },
        }
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Something went wrong: {str(e)}")
