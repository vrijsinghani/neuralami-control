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
    PYTHONPATH=/app

# Add build arguments for version and commit
ARG VERSION=latest
ARG COMMIT=unknown
ARG COMMIT_DATE
ENV VERSION=$VERSION
ENV COMMIT=$COMMIT
ENV COMMIT_DATE=$COMMIT_DATE

# Install runtime dependencies and UV
RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh

# Create directory for env files
RUN mkdir -p /app/env-files

WORKDIR /app

# Copy requirements file
COPY requirements.txt ./

# Create venv and install dependencies
RUN uv venv /app/.venv && \
    . /app/.venv/bin/activate && \
    uv pip install -r requirements.txt

# Copy example env file
COPY env-files/.env.example /app/env-files/

# Copy only necessary application files
COPY apps ./apps
COPY home ./home
COPY config ./config
COPY file_manager ./file_manager
COPY locale ./locale
COPY staticfiles ./staticfiles
COPY templates ./templates
COPY core ./core
RUN mkdir -p /app/logs

# Ensure we use the venv python
ENV PATH="/app/.venv/bin:$PATH"

CMD ["celery", "-A", "apps.tasks", "worker", "-l", "info", "-B"]