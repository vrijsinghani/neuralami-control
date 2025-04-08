# Use Microsoft's Playwright Python image as base with specific version
FROM mcr.microsoft.com/playwright/python:v1.46.0-jammy

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py entrypoint.sh ./

# Expose port (default, can be overridden by environment)
EXPOSE 8000

# Set environment variables
ENV PORT=8000
ENV PYTHONUNBUFFERED=1

# Make entrypoint script executable
RUN chmod +x /app/entrypoint.sh

# Install curl for healthcheck
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Add healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:$PORT/health || exit 1

# Run the application using the entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]
