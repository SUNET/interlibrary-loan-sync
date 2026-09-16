FROM python:3.14.7-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies (expects pyproject.toml or requirements.txt in the build context)
COPY pyproject.toml* requirements.txt* ./
# Copy the entire project first so README.md and other metadata files are present
COPY . .
RUN pip install --no-cache-dir --upgrade pip \
    && if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi \
    && if [ -f pyproject.toml ]; then pip install --no-cache-dir .; fi

# Copy application source code
COPY . .

# Default command (can be overridden via docker-compose)
CMD ["uvicorn", "ill_bridge.api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
