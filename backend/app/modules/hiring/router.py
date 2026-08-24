from fastapi import APIRouter

# Placeholder. The Hiring Assistant module is a thin layer on top of the voice core
# (app/modules/voice/) built in a later phase - GET /api/agents now lives there.
router = APIRouter(prefix="/hiring", tags=["hiring"])
