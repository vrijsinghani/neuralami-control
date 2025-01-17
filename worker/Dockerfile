FROM python:3.10-slim-bullseye

WORKDIR /app

# Copy project files
COPY pyproject.toml poetry.lock ./

# Install Poetry and dependencies
RUN pip install poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --no-root

# Copy application code
COPY apps ./apps
COPY core ./core

ENV PYTHONPATH=/app

CMD ["celery", "-A", "apps.tasks", "worker", "-l", "info"]