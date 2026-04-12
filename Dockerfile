# ============================================
# OnePersonCo - Multi-Stage Docker Build
# ============================================
# Pure Python 3.11, zero external dependencies
# Runs all three products: PasteHut, PingBot, IconForge
# Plus infrastructure: health_check, backup, log cleanup

FROM python:3.11-slim AS base

LABEL maintainer="OnePersonCo"
LABEL description="One-Person SaaS Company - IconForge + PasteHut + PingBot"

# System deps (minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY . /app/

# Create data directories
RUN mkdir -p /data/pastehut /data/pingbot /data/iconforge /data/backups /data/logs

# Environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV DATA_DIR=/data

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 /app/infrastructure/monitoring/health_check.py --quiet || exit 1

# Default: run PasteHut on port 8080
EXPOSE 8080 8081

# ============================================
# Service entrypoints (select via CMD)
# ============================================

# PasteHut - Paste sharing service
CMD ["python3", "/app/products/paste-hut/server.py"]

# Alternative commands:
# PingBot:     docker run ... python3 /app/products/ping-bot/monitor.py
# IconForge:   docker run ... python3 /app/products/icon-forge/generate.py
# Health:      docker run ... python3 /app/infrastructure/monitoring/health_check.py
# Backup:      docker run ... python3 /app/infrastructure/cron/backup_db.py
# Clean logs:  docker run ... python3 /app/infrastructure/cron/clean_logs.py
