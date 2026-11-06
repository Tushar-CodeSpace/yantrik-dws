FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    YANTRIK_PORT=8000

WORKDIR /app

# Install system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY pyproject.toml requirements.txt /app/
COPY src/ /app/src/

# Expose HTTP port
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["python3", "src/yantrik_dws/server.py"]
