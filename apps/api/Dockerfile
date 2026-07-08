# Backend image. Multi-stage: build wheels with uv, then a slim runtime.
# Finalized in M0.T7; this scaffold is functional but not size-optimized.

# --- builder ---------------------------------------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/venv

RUN pip install --no-cache-dir uv==0.4.20

WORKDIR /build
# uv.lock must be present so --frozen installs the locked set into /venv (the env
# we ship). Without UV_PROJECT_ENVIRONMENT, uv syncs into ./.venv and /venv holds
# only the bare interpreter — uvicorn/alembic then missing at runtime.
COPY apps/api/pyproject.toml apps/api/uv.lock apps/api/README.md ./
COPY apps/api/app ./app
RUN uv sync --no-dev --frozen

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
# Methodology seed templates — resolved at runtime by app/methodology/templates.py
# (walks up to packages/methodology-templates).
COPY packages/methodology-templates ./packages/methodology-templates

USER krititva
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
