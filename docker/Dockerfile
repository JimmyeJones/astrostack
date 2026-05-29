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

# Install Python deps first (better layer caching). Copy the source needed for
# the build backend to resolve the package, then install with the web extra.
COPY pyproject.toml README.md ./
COPY seestack/ ./seestack/
COPY webapp/ ./webapp/

# Bring in the built SPA so it's packaged into webapp/static.
COPY --from=frontend /build/dist/ ./webapp/static/

RUN pip install --no-cache-dir .[web]

# ASTAP headless plate solver + d05 star database (500 stars/sq.deg; sufficient
# for the Seestar's ~1.3° FOV).  Downloaded at image-build time from SourceForge
# so users don't have to bundle anything manually.
# Override at runtime by mounting a different install over /opt/astap (see
# docker-compose.yml) or by setting astap_path in the Settings page.
RUN apt-get update && apt-get install -y --no-install-recommends curl unzip \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /opt/astap \
    \
    # ASTAP headless CLI binary (Linux x86_64)
    && curl -fsSL -o /tmp/astap_cli.zip \
         "https://sourceforge.net/projects/astap-program/files/linux_installer/astap_command-line_version_Linux_amd64.zip/download" \
    && unzip -j /tmp/astap_cli.zip -d /opt/astap \
    && mv /opt/astap/astap_cli /opt/astap/astap \
    && chmod +x /opt/astap/astap \
    && rm /tmp/astap_cli.zip \
    \
    # d05 star database (.290 index files)
    && curl -fsSL -o /tmp/d05.deb \
         "https://sourceforge.net/projects/astap-program/files/star_databases/d05_star_database.deb/download" \
    && dpkg -x /tmp/d05.deb /tmp/d05 \
    && find /tmp/d05 -name "*.290" -exec mv {} /opt/astap/ \; \
    && rm -rf /tmp/d05.deb /tmp/d05 \
    \
    # Remove build-time tools to keep the layer lean
    && apt-get purge -y --auto-remove curl unzip

ENV SEESTACK_ASTAP_PATH=/opt/astap/astap
ENV ASTROSTACK_DATA=/data
ENV ASTROSTACK_PORT=8000
# Import seestack/webapp (and the built webapp/static) from the source tree in
# /app, so the SPA is found regardless of wheel package-data behaviour.
ENV PYTHONPATH=/app

EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health').status==200 else 1)"

CMD ["uvicorn", "webapp.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
