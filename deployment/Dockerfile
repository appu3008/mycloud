# deployment/Dockerfile — used only when Docker is installed (see notes in
# docker-compose.yml). Primary deployment remains systemd + reverse proxy.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies only; source mounted/copied next for layer caching.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/app backend/app
COPY backend/migrations backend/migrations

# Data paths are volumes: /app/storage, /app/database, /app/backups
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
