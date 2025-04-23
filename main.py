from fastapi import FastAPI
from routes.auth.auth import router as auth_router
from routes.chat.chat import router as chat_router

from config import Base, engine
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(root_path="/api")
# init_orm_db()

# Create DB tables
Base.metadata.create_all(bind=engine)
origins = [
    "https://yashraa.ai",
    "http://localhost:3000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # frontend origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/api")
async def api_root():
    return {"message": "Backend API root working!"}
# orm
app.include_router(auth_router, prefix="/api/auth")
app.include_router(chat_router, prefix="/api/chatbot")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


