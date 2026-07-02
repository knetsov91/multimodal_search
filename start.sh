#!/bin/bash
celery -A celery_app worker --loglevel=info &
exec uvicorn api:app --host 0.0.0.0 --port 8081 --workers 1
