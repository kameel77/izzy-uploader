FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml READ.md /app/
COPY src /app/src

RUN pip install --upgrade pip \
    && pip install -e '.[web]'

ENV FLASK_APP=izzy_uploader_web.app \
    IZZY_UPLOADER_STATE_FILE=/data/state.json \
    IZZY_UPLOADER_LOCATION_MAP_FILE=/data/location_map.json \
    IZZY_UPLOADER_WEB_SECRET=change-me

VOLUME ["/data"]

EXPOSE 8000

CMD ["gunicorn", "izzy_uploader_web:create_app", "--bind", "0.0.0.0:8000", "--workers", "2"]
