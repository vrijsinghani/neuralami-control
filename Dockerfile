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

# Set default environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_HOME="/opt/poetry" \
    PATH="/opt/poetry/bin:$PATH"

# Create directory for env files (will be mounted at runtime)
RUN mkdir -p /app/env-files

# Copy example env file only
COPY env-files/.env.example /app/env-files/

ENV PATH="/root/.cargo/bin:$PATH"

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | POETRY_HOME=/opt/poetry python3 - && \
    chmod a+x /opt/poetry/bin/poetry

WORKDIR /app

COPY pyproject.toml poetry.lock ./
# Configure poetry and install dependencies
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --no-root

COPY . .

COPY start_daphne.sh /app/start_daphne.sh
RUN chmod +x /app/start_daphne.sh

# Make sure the script uses Unix line endings
RUN sed -i 's/\r$//' /app/start_daphne.sh

EXPOSE ${APP_PORT:-3010}

CMD ["/app/start_daphne.sh"]