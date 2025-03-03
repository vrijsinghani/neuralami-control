# Build stage for SQLite and dependencies
FROM python:3.10-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    wget \
    build-essential \
    libssl-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Install updated SQLite
RUN wget https://www.sqlite.org/2024/sqlite-autoconf-3450000.tar.gz \
    && tar xvfz sqlite-autoconf-3450000.tar.gz \
    && cd sqlite-autoconf-3450000 \
    && ./configure \
    && make \
    && make install \
    && cd .. \
    && rm -rf sqlite-autoconf-3450000 \
    && rm sqlite-autoconf-3450000.tar.gz

# Final stage
FROM python:3.10-slim

# Copy SQLite from builder
COPY --from=builder /usr/local/lib/libsqlite3* /usr/local/lib/
COPY --from=builder /usr/local/bin/sqlite3 /usr/local/bin/
COPY --from=builder /usr/local/include/sqlite3*.h /usr/local/include/

# Update library path to use new SQLite
ENV LD_LIBRARY_PATH=/usr/local/lib

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    POETRY_VERSION=1.7.1 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_CREATE=false \
    PATH="/opt/poetry/bin:$PATH"

# Install runtime dependencies and Poetry
RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -sSL https://install.python-poetry.org | python3 - \
    && poetry --version

# Create directory for env files
RUN mkdir -p /app/env-files

WORKDIR /app

# Copy Poetry configuration files
COPY pyproject.toml poetry.lock ./

# Install dependencies - using the older no-dev syntax
RUN poetry install --no-interaction --no-ansi --no-dev

# Copy example env file
COPY env-files/.env.example /app/env-files/

# Copy only necessary application files
COPY apps ./apps
COPY core ./core

CMD ["celery", "-A", "apps.tasks", "worker", "-l", "info"]