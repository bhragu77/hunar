from fastapi import APIRouter

from app.api.webhooks import router as webhooks_router
from app.modules.attendance.router import router as attendance_router
from app.modules.hiring.router import router as hiring_router
from app.modules.outreach.router import router as outreach_router
from app.modules.people_search.router import router as people_search_router
from app.modules.voice.router import router as voice_router

api_router = APIRouter(prefix="/api")

api_router.include_router(voice_router)
api_router.include_router(hiring_router)
api_router.include_router(people_search_router)
api_router.include_router(outreach_router)
api_router.include_router(attendance_router)
api_router.include_router(webhooks_router)
