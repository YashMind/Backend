from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class ApiKeyRequest(BaseModel):
    tool: str
    api_key: str

@router.post("/save-key")
async def save_api_key(data: ApiKeyRequest):
    try:
        # Read current keys if file exists
        keys = {}
        try:
            with open("keys.txt", "r") as f:
                for line in f:
                    if ":" in line:
                        k, v = line.strip().split(":", 1)
                        keys[k.strip()] = v.strip()
        except FileNotFoundError:
            pass

        # Update or add the key for the tool
        keys[data.tool] = data.api_key

        # Write back all keys
        with open("keys.txt", "w") as f:
            for k, v in keys.items():
                f.write(f"{k}: {v}\n")

        return {"message": f"API key Saved Sucessfully!!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
