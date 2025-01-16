FROM python:3.9-slim-buster

WORKDIR /app

# Install system dependencies if needed (example for Playwright or other tools)
# If your tasks use system level tools such as playwright you need to install them here
# RUN apt-get update && apt-get install -y <system-packages> && \
#     apt-get clean && rm -rf /var/lib/apt/lists/*
# Example for playwright
# RUN apt-get update && apt-get install -y libx11-xcb1 libxcomposite1 libxcursor1 libxdamage1 libxi6 libxtst6 libnss3 libgconf-2-4 libasound2 libatk1.0-0 libatk-bridge2.0-0 libgtk-3-0 libwebkit2gtk-4.0-37 libxrandr2 libcups2 && apt-get clean && rm -rf /var/lib/apt/lists/*
# If you are using rust based tools you would install rust here as well as cargo

# Copy Poetry files and install dependencies
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --no-root

# Copy only the necessary application code (adjust paths as needed)
COPY apps/tasks /app/apps/tasks
COPY apps/agents /app/apps/agents
COPY apps/common /app/apps/common
COPY apps/image_optimizer /app/apps/image_optimizer
COPY apps/seo_audit /app/apps/seo_audit
#If there are any other direct dependencies that tasks have
COPY apps/other_dep /app/apps/other_dep
# If needed copy settings or other modules
COPY core /app/core
COPY manage.py /app/manage.py
# If you need to make database migrations available
COPY migrations /app/migrations

# Set correct permissions if needed (if your app requires specific user/group)
# RUN chown -R app:app /app

# Celery worker command
CMD ["celery", "-A", "apps.tasks", "worker", "-l", "info"]