# Build context is the repo root (not ./backend) so this image can also bake in docs/ - see
# docker-compose.yml (context: .) and render.yaml (dockerContext: .). A cloud deploy has no
# host filesystem to bind-mount docs/ from the way local docker-compose optionally does, so
# the Attendance module's Design tab needs it baked into the image to work there too.
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY docs/ /app/docs

EXPOSE 8000
# $PORT is set by Render/Railway (and unset under docker-compose, where it falls back to the
# EXPOSE'd 8000 that docker-compose.yml's host port mapping already targets) - shell form so
# the variable actually expands, since the exec form doesn't invoke a shell.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
