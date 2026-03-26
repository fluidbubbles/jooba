from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "jooba",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_transport_options={"visibility_timeout": 7200},
    beat_schedule={
        "send-due-emails": {
            "task": "app.tasks.scheduler.send_due_emails",
            "schedule": 30.0,
        },
    },
)

celery_app.conf.update(
    include=["app.tasks.scheduler", "app.tasks.email_sending"],
)
