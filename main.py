from fastapi import FastAPI
from routes.auth.auth import router as auth_router
from routes.chat.chat import router as chat_router
from routes.chat.tuning import router as tuning_router
from routes.chat.appearance import router as appearance_router
from routes.chat.slack import router as slack_router
from routes.chat.whatsapp import router as whatsapp_router
from routes.admin.admin import router as admin_router
from routes.supportTickets.routes import router as support_router
from fastapi.staticfiles import StaticFiles
from routes.activitylog.activitylog import router as activity_log_router
from routes.admin.announcement import router as announcement_router
from routes.admin.notice import router as notice_router
from routes.admin.product import router as product_router
from routes.admin.tools import router as tool_router
from routes.admin.volumndiscount import router as volumn_router
from config import Base, engine
from fastapi.middleware.cors import CORSMiddleware
from routes.admin.apikeys import router as apikeys_router

app = FastAPI()
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

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/api")
async def api_root():
    return {"message": "Backend API root working!"}
# orm
app.include_router(auth_router, prefix="/api/auth")
app.include_router(chat_router, prefix="/api/chatbot")
app.include_router(tuning_router, prefix="/api/tuning")
app.include_router(appearance_router, prefix="/api/appearance")
app.include_router(admin_router, prefix="/api/admin")
app.include_router(slack_router, prefix="/api/slack")
app.include_router(support_router, prefix="/api/tickets")
app.include_router(activity_log_router, prefix="/api/activity")
app.include_router(whatsapp_router, prefix="/api/whatsapp")
app.include_router(announcement_router, prefix="/api/admin")
app.include_router(notice_router, prefix="/api/admin")
app.include_router(product_router, prefix="/api/admin")
app.include_router(tool_router, prefix="/api/admin")
app.include_router(volumn_router, prefix="/api/admin")
app.include_router(apikeys_router, prefix="/api/admin")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


