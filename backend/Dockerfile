FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# curl is kept for optional container-level healthchecks.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# Install the package + dependencies. (asyncpg and bcrypt ship wheels.)
COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
RUN pip install --upgrade pip && pip install -e .

EXPOSE 8000

# Default command; compose overrides it to run migrations first.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
