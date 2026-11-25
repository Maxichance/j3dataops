FROM python:3.12-slim-bookworm

# Binaire uv officiel, tag figé (jamais latest)
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:${PATH}" \
    PORT=8080

WORKDIR /app

# 1. Dépendances d'abord (cache Docker), figées par uv.lock, sans pytest ni ruff
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-cache

# 2. Code applicatif uniquement
COPY src/ ./src/

# 3. Jamais root
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080
# Cloud Run impose 0.0.0.0 et le port fourni dans $PORT
CMD ["sh", "-c", "exec uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
