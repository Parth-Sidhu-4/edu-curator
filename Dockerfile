# =============================================================================
# STAGE 1: Builder — installs all deps + compilers, then gets thrown away
# =============================================================================
FROM python:3.11-slim-bookworm AS builder

WORKDIR /build

# Install build-time-only system deps (C compilers for native extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install CPU-only PyTorch FIRST to prevent the 4GB GPU version
RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu

# Install all other Python deps
RUN pip install --no-cache-dir -r requirements.txt

# =============================================================================
# STAGE 2: Runner — lean production image (no compilers, no build cache)
# =============================================================================
FROM python:3.11-slim-bookworm AS runner

# Runtime-only system libs (no build-essential = saves ~300MB)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

WORKDIR /app

# Copy installed Python packages from the builder (no compiler bloat!)
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Install Playwright Chromium ONLY (skip Firefox/WebKit to save ~500MB)
RUN playwright install --with-deps chromium

# Copy application code
COPY . .

EXPOSE 8502

# SEC-08: Run as a non-root user to limit blast radius from container compromise.
RUN groupadd -r curator && useradd -r -g curator --home /app curator \
    && chown -R curator:curator /app
USER curator

CMD ["python", "dashboard/serve.py"]
