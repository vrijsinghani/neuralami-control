FROM python:3.10.4

# Install system dependencies including updated SQLite
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

# Update library path to use new SQLite
ENV LD_LIBRARY_PATH=/usr/local/lib:${LD_LIBRARY_PATH:-}

# Build arguments with defaults
ARG DJANGO_ENV=staging

# Set default environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_HOME="/opt/poetry" \
    PATH="/opt/poetry/bin:$PATH" \
    DJANGO_ENV=${DJANGO_ENV:-development}

# Create directory for env files
RUN mkdir -p /app/env-files

# Copy env files
COPY env-files/.env.example /app/env-files/
COPY env-files/.env.${DJANGO_ENV} /app/env-files/

# Debug: Print which env file we're using
RUN echo "Using environment file: /app/env-files/.env.${DJANGO_ENV}"
RUN cp /app/env-files/.env.${DJANGO_ENV} /app/.env

ENV PATH="/root/.cargo/bin:$PATH"

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | POETRY_HOME=/opt/poetry python3 - && \
    chmod a+x /opt/poetry/bin/poetry

WORKDIR /app

COPY pyproject.toml poetry.lock ./
# Configure poetry and install dependencies
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --no-root

RUN poetry config virtualenvs.create false 

COPY . .
# Source environment variables from the appropriate file
RUN echo "source /app/.env" >> /root/.bashrc

RUN python manage.py collectstatic --no-input
RUN python manage.py makemigrations
RUN python manage.py migrate



COPY start_daphne.sh /app/start_daphne.sh
RUN chmod +x /app/start_daphne.sh

# Make sure the script uses Unix line endings
RUN sed -i 's/\r$//' /app/start_daphne.sh

EXPOSE ${APP_PORT:-3010}

CMD ["/app/start_daphne.sh"]