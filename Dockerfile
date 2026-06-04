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

# Strip dev/test deps (everything from the Dev/Test comment onwards) before
# installing — pytest must never land in the production image.
RUN sed '/^# ── Dev/,$d' requirements.txt > requirements.prod.txt

# Install CPU-only PyTorch FIRST to prevent the 4GB GPU version being pulled in
RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu

# Install all other Python prod deps (no pytest, no test tooling)
RUN pip install --no-cache-dir -r requirements.prod.txt

# =============================================================================
# STAGE 2: Runner — lean production image (no compilers, no build cache)
# =============================================================================
FROM python:3.11-slim-bookworm AS runner

# Runtime-only system libs required by sentence-transformers / numpy
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python environment hardening
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

# Disable Playwright by default — saves ~500MB on Railway free tier.
# Set PLAYWRIGHT_ENABLED=true + uncomment the playwright install line below
# if web-crawling of JS-rendered pages is needed.
ENV PLAYWRIGHT_ENABLED=false

WORKDIR /app

# Copy installed Python packages from the builder stage (no compiler bloat)
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Uncomment only if PLAYWRIGHT_ENABLED=true — adds ~500MB to the image
# RUN playwright install --with-deps chromium

# Copy application code (respects .dockerignore — secrets are excluded)
COPY . .

# Create data directories that must exist at runtime
# (volumes or Railway's ephemeral storage will overlay this at runtime)
RUN mkdir -p data/uploads data/logs data/chunks data/extractions \
             data/knowledge data/generated data/mappings data/seed

# SEC-08: Run as a non-root user to limit blast radius from container compromise.
RUN groupadd -r curator && useradd -r -g curator --home /app curator \
    && chown -R curator:curator /app
USER curator

# Railway injects $PORT at runtime — the app reads it via os.getenv("PORT").
# EXPOSE is documentation only; Railway ignores it and uses $PORT.
EXPOSE 8502

# Health check so Railway knows when the container is ready
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8502}/health || exit 1

CMD ["python", "dashboard/serve.py"]
