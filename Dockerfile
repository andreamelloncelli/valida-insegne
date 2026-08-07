FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Le dipendenze stanno in un livello separato: si reinstallano solo quando
# cambiano pyproject.toml o uv.lock, non a ogni modifica del sorgente.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH" \
    PORT=8080

RUN useradd --create-home --uid 1000 app && chown -R app:app /app
USER app

EXPOSE 8080

# Forma shell: serve a espandere $PORT, che Railway assegna a runtime.
CMD streamlit run src/silverc/Validazione.py \
    --server.address=0.0.0.0 \
    --server.port=$PORT \
    --server.headless=true \
    --server.maxUploadSize=10 \
    --browser.gatherUsageStats=false
