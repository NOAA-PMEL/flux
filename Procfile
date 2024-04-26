worker-default: celery -A app:celery_app worker --loglevel DEBUG --concurrency=6
worker-beat: celery -A app:celery_app beat
web: gunicorn app:server --workers 4


