FROM node:22-bookworm-slim@sha256:5ec23b7c622b00547753bc6ffd78085dd868a68aeb41c8e0a1418f033e13d96d AS frontend
WORKDIR /src
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim@sha256:09a17cad02668ae61ece136b4fd36ac3849e14f670ebedb637ea3e15580525bc AS python-base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

FROM python-base AS simulator
COPY simulator/ ./simulator/
CMD ["python", "-m", "simulator.run"]

FROM python-base AS app
COPY backend/requirements.lock .
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.lock && python -m pip check
COPY backend/ ./
COPY --from=frontend /src/dist ./static
CMD ["sh", "-ec", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
