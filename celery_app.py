from celery import Celery
from kombu import Queue
import os

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672//")
POSTGRES_USERNAME = os.getenv("POSTGRES_USERNAME", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
RESULT_BACKEND = f"db+postgresql://{POSTGRES_USERNAME}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}/recipes"

celery_app = Celery(
    "multimodal_search",
    broker=RABBITMQ_URL,
    backend=RESULT_BACKEND,
    include=["tasks.recipe_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    result_expires=3600,
    task_queues=(
        Queue("celery", durable=True),
    ),
    task_default_queue="celery",
    worker_pool="solo",
)
