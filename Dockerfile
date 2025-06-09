# Use Python 3.11 slim image for smaller size
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create app user for security
RUN groupadd -r meshcord && useradd -r -g meshcord meshcord

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY meshcord_bot.py .

# Create data directory for SQLite database
RUN mkdir -p /app/data && chown -R meshcord:meshcord /app

# Switch to non-root user
USER meshcord

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import sqlite3; conn = sqlite3.connect('/app/data/message_tracking.db'); conn.close()" || exit 1

# Expose port (if needed for future web interface)
EXPOSE 8080

# Run the bot
CMD ["python", "meshcord_bot.py"]