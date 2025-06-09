# Multi-stage build for smaller final image
FROM python:3.10-slim as builder

# Set build-time environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.10-slim as production

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    # For health checks and debugging
    sqlite3 \
    # For signal handling
    procps \
    # Clean up
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create app user and group with specific UID/GID for security
RUN groupadd -r -g 1001 meshcord && \
    useradd -r -g meshcord -u 1001 -d /app -s /bin/bash meshcord

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Set working directory
WORKDIR /app

# Copy application code with proper ownership
COPY --chown=meshcord:meshcord meshcord_bot.py .

# Create data directory with proper permissions
RUN mkdir -p /app/data && \
    chown -R meshcord:meshcord /app && \
    chmod 755 /app && \
    chmod 755 /app/data

# Create health check script
RUN echo '#!/bin/bash\n\
import sqlite3\n\
import sys\n\
import os\n\
\n\
try:\n\
    # Check if database file exists\n\
    if not os.path.exists("/app/data/message_tracking.db"):\n\
        print("Database file not found")\n\
        sys.exit(1)\n\
    \n\
    # Check database integrity\n\
    conn = sqlite3.connect("/app/data/message_tracking.db")\n\
    cursor = conn.cursor()\n\
    \n\
    # Verify required tables exist\n\
    cursor.execute("SELECT name FROM sqlite_master WHERE type=\"table\"")\n\
    tables = [row[0] for row in cursor.fetchall()]\n\
    required_tables = ["processed_messages", "nodes", "radios"]\n\
    \n\
    for table in required_tables:\n\
        if table not in tables:\n\
            print(f"Required table {table} missing")\n\
            sys.exit(1)\n\
    \n\
    # Test a simple query\n\
    cursor.execute("SELECT COUNT(*) FROM processed_messages")\n\
    cursor.fetchone()\n\
    \n\
    conn.close()\n\
    print("Health check passed")\n\
    sys.exit(0)\n\
    \n\
except Exception as e:\n\
    print(f"Health check failed: {e}")\n\
    sys.exit(1)\n\
' > /app/healthcheck.py && \
    chmod +x /app/healthcheck.py && \
    chown meshcord:meshcord /app/healthcheck.py

# Switch to non-root user
USER meshcord

# Health check with improved script
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python /app/healthcheck.py

# Expose port for potential future web interface
EXPOSE 8080

# Add metadata labels
LABEL maintainer="meshcord-team" \
      version="1.0.0" \
      description="Meshtastic Discord Bridge" \
      org.opencontainers.image.source="https://github.com/sargonas/meshcord" \
      org.opencontainers.image.title="Meshcord" \
      org.opencontainers.image.description="A Discord bridge for Meshtastic networks"

# Use exec form for better signal handling
CMD ["python", "meshcord_bot.py"]