from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.enrollments import router as enrollments_router
from app.api.exception_handlers import register_exception_handlers
from app.api.health import router as health_router
from app.api.inbox import router as inbox_router
from app.api.nylas import router as nylas_router
from app.api.replies import router as replies_router
from app.api.sequences import router as sequences_router
from app.api.unsubscribe import router as unsubscribe_router
from app.api.webhooks import router as webhooks_router

app = FastAPI(title="Jooba", description="Recruiter outreach automation")

register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(sequences_router)
app.include_router(enrollments_router)
app.include_router(nylas_router)
app.include_router(unsubscribe_router)
app.include_router(webhooks_router)
app.include_router(inbox_router)
app.include_router(replies_router)
