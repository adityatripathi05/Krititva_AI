# Backend image. Multi-stage: build wheels with uv, then a slim runtime.
# Finalized in M0.T7; this scaffold is functional but not size-optimized.

# --- builder ---------------------------------------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

RUN pip install --no-cache-dir uv==0.4.20

WORKDIR /build
COPY apps/api/pyproject.toml apps/api/README.md ./
COPY apps/api/app ./app
RUN uv venv /venv && \
    VIRTUAL_ENV=/venv uv sync --no-dev --frozen 2>/dev/null || \
    VIRTUAL_ENV=/venv uv sync --no-dev

# --- runtime ---------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/venv/bin:$PATH"

RUN useradd -m -u 1000 krititva
WORKDIR /app

COPY --from=builder /venv /venv
COPY apps/api/app ./app
COPY apps/api/alembic.ini ./alembic.ini

USER krititva
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
