from fastapi import FastAPI
# from auth.auth import router as auth_router
from routes.auth.auth import router as auth_router
from routes.chat.chat import router as chat_router
# from products.ormProducts import router as products_orm_router
# from cron.cron import scheduler 
# from config import init_orm_db

from config import Base, engine
from fastapi.middleware.cors import CORSMiddleware
# from routes import auth

app = FastAPI()
# init_orm_db()

# Create DB tables
Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # frontend origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# orm
app.include_router(auth_router, prefix="/api/auth")
app.include_router(chat_router, prefix="/api/bot")

@app.get("/")
async def root():
    return {"message": "Hello World"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


