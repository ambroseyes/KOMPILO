FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# No system packages needed: asyncpg and bcrypt ship manylinux wheels.
# Install the package + dependencies.
COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
RUN pip install --upgrade pip && pip install -e .

EXPOSE 8000

# Default command; compose overrides it to run migrations first.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
