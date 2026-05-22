# HPDF TDS Tools — Docker image
#
# Provides tds_render.py (MD → DOCX) and tds_unconvert.py (DOCX → MD)
# with all runtime dependencies baked in:
#   • pandoc          — Markdown ↔ DOCX conversion
#   • Chromium        — headless browser for Mermaid diagram rendering
#   • mmdc            — Mermaid CLI (wraps Puppeteer + Chromium)
#   • python-docx     — cover-page and DOCX manipulation
#
# Usage (via the `tds` wrapper script — see docker/tds):
#   tds render   HPDF_TDS_0001_example.md
#   tds unrender HPDF_TDS_0001_example.docx
#
# To build and push manually:
#   docker build -t hpdf/tds-tools:latest .
#   docker push hpdf/tds-tools:latest

FROM node:20-bookworm-slim

# ── Environment ────────────────────────────────────────────────────────────────

ENV DEBIAN_FRONTEND=noninteractive \
    # Tell Puppeteer/mmdc not to download its own Chrome bundle —
    # we install the system Chromium below.
    PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

# ── System dependencies ────────────────────────────────────────────────────────

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        pandoc \
        chromium \
        # Font needed so Mermaid diagrams render text correctly
        fonts-liberation \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ────────────────────────────────────────────────────────

# python-docx: used by tds_cover.py (cover page) and tds_unconvert.py (DOCX stripping)
RUN pip3 install --break-system-packages python-docx

# ── Mermaid CLI ────────────────────────────────────────────────────────────────

RUN npm install -g @mermaid-js/mermaid-cli

# Puppeteer/Chrome will not run as root without --no-sandbox.
# Store a config file and wrap the mmdc binary to always inject it,
# so tds_render.py can call `mmdc` without needing to know about this.
RUN printf '{"args":["--no-sandbox","--disable-setuid-sandbox","--disable-dev-shm-usage"]}\n' \
        > /etc/puppeteer-config.json \
 && mv /usr/local/bin/mmdc /usr/local/bin/mmdc-real \
 && printf '#!/bin/sh\nexec /usr/local/bin/mmdc-real --puppeteerConfigFile /etc/puppeteer-config.json "$@"\n' \
        > /usr/local/bin/mmdc \
 && chmod +x /usr/local/bin/mmdc

# ── Application files ──────────────────────────────────────────────────────────
#
# Layout mirrors the workspace structure the scripts expect:
#   /app/scripts/  — Python scripts + Lua filter
#   /app/resources/ — Reference DOCX template + HPDF logo
#
# tds_render.py discovers resources via:
#   Path(__file__).parent.parent / 'resources' / '...'
# which resolves to /app/resources/ — matching the layout below.

COPY scripts/ /app/scripts/
COPY resources/ /app/resources/

# Ensure all app files are world-readable so they remain accessible when
# the container runs as an arbitrary non-root UID (via --user in the wrapper).
RUN chmod -R a+rX /app

# ── Runtime ────────────────────────────────────────────────────────────────────

# /workspace is the mount point for the user's TDS directory.
# The `tds` wrapper script mounts $(pwd) here at runtime.
WORKDIR /workspace
