FROM python:3.10.4

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_HOME="/opt/poetry" \
    PATH="/opt/poetry/bin:$PATH" \
    APP_PORT=3010

# Install system dependencies
RUN apt-get update && \
    apt-get install -y \
        libx11-xcb1 libxcomposite1 libxcursor1 libxdamage1 \
        libxi6 libxtst6 libnss3 libgconf-2-4 libasound2 \
        libatk1.0-0 libatk-bridge2.0-0 libgtk-3-0 \
        libwebkit2gtk-4.0-37 libxrandr2 libcups2 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.cargo/bin:$PATH"

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | POETRY_HOME=/opt/poetry python3 - && \
    chmod a+x /opt/poetry/bin/poetry

WORKDIR /app

COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --no-root && \
    playwright install --with-deps

COPY . .

RUN python manage.py collectstatic --no-input
RUN python manage.py makemigrations
RUN python manage.py migrate

COPY start_daphne.sh /app/start_daphne.sh
RUN chmod +x /app/start_daphne.sh

EXPOSE ${APP_PORT}

CMD ["/app/start_daphne.sh"]