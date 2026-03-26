import logging
from abc import ABC, abstractmethod
from collections.abc import Callable

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


class TaskDispatcher(ABC):
    @abstractmethod
    def dispatch(self, task_name: str, *args: object, **kwargs: object) -> None:
        ...


class CeleryDispatcher(TaskDispatcher):
    """Production — dispatches to Celery queues."""

    def dispatch(self, task_name: str, *args: object, **kwargs: object) -> None:
        queue = kwargs.pop("queue", "default")
        celery_app.send_task(task_name, args=args, kwargs=kwargs, queue=queue)


class SyncDispatcher(TaskDispatcher):
    """Testing — executes task function immediately, no queue."""

    def __init__(self) -> None:
        self._registry: dict[str, Callable] = {}

    def register(self, task_name: str, func: Callable) -> None:
        self._registry[task_name] = func

    def dispatch(self, task_name: str, *args: object, **kwargs: object) -> None:
        kwargs.pop("queue", None)
        func = self._registry.get(task_name)
        if not func:
            logger.warning("[SyncDispatcher] No handler for %s", task_name)
            return
        func(*args, **kwargs)


def get_dispatcher() -> TaskDispatcher:
    """Always Celery in production: EMAIL_PROVIDER=mock swaps MockSender only.

    Beat and workers must still enqueue tasks; SyncDispatcher is test-only and
    has no handlers when the app runs for real.
    """
    return CeleryDispatcher()
