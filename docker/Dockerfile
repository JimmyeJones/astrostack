# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1 — build the React SPA
# ---------------------------------------------------------------------------
FROM node:20-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
# Vite is configured to emit into ../webapp/static; redirect it here instead.
RUN npm run build -- --outDir /build/dist --emptyOutDir

# ---------------------------------------------------------------------------
# Stage 2 — Python runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# OS libraries the engine needs (Pillow, scikit-image, numpy/scipy runtime).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ASTAP headless plate solver + d05 star database (500 stars/sq.deg; sufficient
# for the Seestar's ~1.3° FOV). Fetched at image-build time so users don't have
# to bundle anything manually. install-astap.sh tries several download sources
# in turn and verifies the binary actually runs — a broken URL fails the build
# loudly instead of producing a silently solver-less image.
# Override the database with --build-arg ASTAP_DB=d20 (or mount your own install
# over /opt/astap at runtime; see docker-compose.yml).
#
# IMPORTANT: this block is placed BEFORE copying the app source so that editing
# code doesn't invalidate it. ASTAP (a ~hundreds-of-MB download) is only
# re-fetched when install-astap.sh or ASTAP_DB actually change — not on every
# code update. (Routine rebuilds must NOT use --no-cache, or this is defeated.)
ARG ASTAP_DB=d05
COPY docker/install-astap.sh /tmp/install-astap.sh
RUN apt-get update && apt-get install -y --no-install-recommends curl unzip file \
    && rm -rf /var/lib/apt/lists/* \
    && chmod +x /tmp/install-astap.sh \
    && ASTAP_DB="${ASTAP_DB}" /tmp/install-astap.sh \
    && rm /tmp/install-astap.sh \
    && apt-get purge -y --auto-remove curl unzip file

# Python deps + app source. A BuildKit pip cache keeps downloaded wheels on the
# build host, so a code change reinstalls quickly instead of re-downloading
# numpy/astropy/etc. Source is copied last (it changes most often).
COPY pyproject.toml README.md ./
COPY seestack/ ./seestack/
COPY webapp/ ./webapp/

# Bring in the built SPA so it's packaged into webapp/static.
COPY --from=frontend /build/dist/ ./webapp/static/

RUN --mount=type=cache,target=/root/.cache/pip pip install .[web]

ENV SEESTACK_ASTAP_PATH=/opt/astap/astap
ENV ASTROSTACK_DATA=/data
ENV ASTROSTACK_PORT=8000
# Import seestack/webapp (and the built webapp/static) from the source tree in
# /app, so the SPA is found regardless of wheel package-data behaviour.
ENV PYTHONPATH=/app

EXPOSE 8000
VOLUME ["/data"]

# Trivial liveness probe with generous slack so a long, CPU-saturating stack
# never trips a restart that would interrupt the running job.
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=6 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health', timeout=10).status==200 else 1)"

CMD ["uvicorn", "webapp.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
