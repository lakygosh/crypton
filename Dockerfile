# Stage 1: Builder
FROM python:3.12-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    libssl-dev \
    python3-dev \
    python3-pip \
    python3-setuptools \
    python3-wheel \
    tzdata \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Upgrade pip and install requirements in correct order
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir build && \
    pip install --no-cache-dir numpy==1.24.4 && \
    pip install --no-cache-dir .

# Stage 2: Runtime
FROM python:3.12-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    tzdata \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user and directories
RUN addgroup --system crypton && \
    adduser --system --ingroup crypton crypton && \
    mkdir -p /home/crypton/app /home/crypton/data /home/crypton/logs && \
    chown -R crypton:crypton /home/crypton

# Set workdir and copy from builder
WORKDIR /home/crypton/app
COPY --from=builder /usr/local /usr/local
COPY . .

# Set permissions
RUN chown -R crypton:crypton /home/crypton/app

# Use non-root user
USER crypton

# Environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=UTC

# Mountable volumes
VOLUME ["/home/crypton/data", "/home/crypton/logs"]

# Default entry
ENTRYPOINT ["python", "-m", "crypton.main"]
CMD ["--help"]