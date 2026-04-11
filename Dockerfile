# Batman Lab — Docker
# Multi-stage build: slim Python image with all dependencies
# Self-hosted: runs anywhere Docker runs

FROM python:3.13-slim AS base

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY batman_flow_engine/requirements.txt /app/batman_flow_engine/requirements.txt
RUN pip install --no-cache-dir -r batman_flow_engine/requirements.txt \
    && pip install --no-cache-dir pytest pytest-timeout ruff

# Copy source code
COPY batman_flow_engine/ /app/batman_flow_engine/
COPY nightwing_agent/ /app/nightwing_agent/

# Create storage directories
RUN mkdir -p /app/batman_flow_engine/storage/reports \
             /app/batman_flow_engine/storage/logs \
             /app/batman_flow_engine/journal \
             /app/nightwing_agent/storage/logs \
             /app/nightwing_agent/storage/ledger

# ─── Stage: Test Runner ───
FROM base AS test
WORKDIR /app/batman_flow_engine
CMD ["python", "-m", "pytest", "tests/", "-q", "--timeout=30"]

# ─── Stage: Batman Engine ───
FROM base AS batman
WORKDIR /app/batman_flow_engine
EXPOSE 8501
# Default: run the engine loop
CMD ["python", "tools/run_loop.py"]

# ─── Stage: Dashboard ───
FROM base AS dashboard
WORKDIR /app/batman_flow_engine
EXPOSE 8501
CMD ["streamlit", "run", "dashboard/app.py", "--server.port=8501", "--server.address=0.0.0.0"]

# ─── Stage: Nightwing Agent ───
FROM base AS nightwing
WORKDIR /app/nightwing_agent
CMD ["python", "agent.py", "--mode", "paper", "--cycles", "0"]
