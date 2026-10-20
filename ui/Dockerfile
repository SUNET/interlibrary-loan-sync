FROM python:3.14.7-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# No system libs needed for the UI (pure Python + httpx2 + nicegui).
# If Pillow / image tooling arrives later, add build-essential here.

# Copy metadata first for better layer caching, then the full project so
# hatchling can find README.md and the ill_bridge_ui/ package tree.
COPY pyproject.toml README.md ./
COPY ill_bridge_ui ./ill_bridge_ui

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

EXPOSE 8080

# Default command runs the admin portal. docker-compose overrides this
# with `command: ill-libris-ui` for the librisportal service.
CMD ["ill-admin-ui"]
