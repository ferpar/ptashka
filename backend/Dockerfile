FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# curl: used by the compose healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv

WORKDIR /app

# Dependencies first, from pyproject.toml alone: this layer stays cached until the dependencies
# change, so editing code doesn't re-download every package.
COPY pyproject.toml .
RUN uv pip install --system --no-cache -r pyproject.toml

# Then the app itself (--no-deps: they're already installed).
COPY src ./src
RUN uv pip install --system --no-cache --no-deps .

COPY alembic.ini .
COPY alembic ./alembic

# Don't run as root: a compromised process gets an unprivileged user, not the container.
RUN useradd --create-home --uid 1000 ptashka
USER ptashka

EXPOSE 8020

# Migrations on every start (safe: they're idempotent; assumes one backend replica at a time).
# `exec` makes uvicorn replace the shell, so it receives Docker's SIGTERM and shuts down gracefully
# (finishing in-flight requests) instead of being killed 10 seconds later.
# --proxy-headers: trust X-Forwarded-* from nginx, so logs show the real client address.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn ptashka.main:app --host 0.0.0.0 --port 8020 --proxy-headers --forwarded-allow-ips='*'"]
