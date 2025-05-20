# Multi-stage build for Crypton trading bot
# Stage 1: Builder
FROM python:3.12-alpine AS builder

# Install build dependencies
RUN apk add --no-cache gcc musl-dev python3-dev libffi-dev

# Set working directory
WORKDIR /app

# Copy requirements from pyproject.toml
COPY pyproject.toml .

# Extract dependencies and install them
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir build && \
    pip install --no-cache-dir .

# Stage 2: Runtime
FROM python:3.12-alpine

# Install runtime dependencies
RUN apk add --no-cache tzdata ca-certificates

# Create non-root user and appropriate directories
RUN addgroup -S crypton && \
    adduser -S -G crypton crypton && \
    mkdir -p /home/crypton/app /home/crypton/data /home/crypton/logs && \
    chown -R crypton:crypton /home/crypton

# Set working directory
WORKDIR /home/crypton/app

# Copy only the necessary files
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/
COPY . .

# Set ownership
RUN chown -R crypton:crypton /home/crypton/app

# Switch to non-root user
USER crypton

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=UTC

# Volume for persistent data and logs
VOLUME ["/home/crypton/data", "/home/crypton/logs"]

# Command to run the application
ENTRYPOINT ["python", "-m", "crypton.main"]
CMD ["--help"]
