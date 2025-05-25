# -------- Stage 1: builder --------
    FROM python:3.12-slim AS builder

    # Build‑time system dependencies
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
    
    WORKDIR /app
    
    # Copy project source and metadata
    COPY . .
    
    # Python dependencies (install numpy first so pandas‑ta works)
    RUN pip install --no-cache-dir --upgrade pip setuptools wheel build && \
        pip install --no-cache-dir numpy==1.24.4 && \
        pip install --no-cache-dir .
    
    # -------- Stage 2: runtime --------
    FROM python:3.12-slim
    
    # Runtime OS deps (no compiler needed here)
    RUN apt-get update && apt-get install -y \
        tzdata \
        ca-certificates \
     && rm -rf /var/lib/apt/lists/*
    
    # Create non‑root user & working dirs
    RUN addgroup --system crypton && \
        adduser --system --ingroup crypton crypton && \
        mkdir -p /home/crypton/app /home/crypton/data /home/crypton/logs && \
        chown -R crypton:crypton /home/crypton
    
    WORKDIR /home/crypton/app
    
    # Copy installed Python libs from builder and project code
    COPY --from=builder /usr/local /usr/local
    COPY . .
    RUN chown -R crypton:crypton /home/crypton/app
    
    USER crypton
    
    ENV PYTHONUNBUFFERED=1 \
        PYTHONDONTWRITEBYTECODE=1 \
        TZ=UTC
    
    VOLUME ["/home/crypton/data", "/home/crypton/logs"]
    
    ENTRYPOINT ["python", "-m", "crypton.main"]
    CMD ["--help"]