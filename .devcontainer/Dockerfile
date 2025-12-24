FROM mcr.microsoft.com/devcontainers/python:1-3.12-bullseye

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 20 for frontend
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs

# Set working directory
WORKDIR /workspace

# Install Python dependencies (will be overwritten by mount, but good for layer caching)
COPY requirements.txt requirements-dev.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt -r requirements-dev.txt

# Default to paper trading
ENV PAPER_TRADING=true
ENV PYTHONPATH=/workspace
