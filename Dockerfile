# Build stage: resolve the locked dependencies into a virtual environment.
FROM python:3.14.10-slim-trixie AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /usr/local/bin/uv

# Copy files into the environment instead of linking to a cache that the
# final image will not have, and never let uv download a different Python.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies change far less often than source, so install them from the
# lock file first and let Docker reuse this layer across code edits.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
RUN uv sync --locked --no-dev --no-editable


# Runtime stage: the environment and nothing else. No uv, no lock file, no
# build cache, and no source tree outside the installed package.
FROM python:3.14.10-slim-trixie

# yfinance keeps a small cache under the home directory, so this user gets one.
RUN groupadd --system --gid 10001 watchtower \
    && useradd --system --uid 10001 --gid watchtower --create-home watchtower

COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER watchtower
WORKDIR /home/watchtower

EXPOSE 8000

# The slim image has no curl. /healthz calls no provider and no database.
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]

# Listen on every interface inside the container. Which host address can
# reach it is decided by the published port, not here.
CMD ["uvicorn", "watchtower.main:app", "--host", "0.0.0.0", "--port", "8000"]
