"""Typed exception hierarchy and FastAPI exception → HTTP mapping.

Services raise these exceptions; route handlers never construct HTTPException
directly. See [`docs/krititva-lld.md`](../../../../docs/krititva-lld.md) §3.2 for the
full error taxonomy.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    """Base for domain exceptions mapped to HTTP responses."""

    http_status: int = 500
    code: str = "internal_error"

    def __init__(self, message: str = "", detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


# ---- 4xx ----------------------------------------------------------------


class NotFound(DomainError):
    http_status = 404
    code = "not_found"


class InvalidCredentials(DomainError):
    http_status = 401
    code = "invalid_credentials"


class InvalidToken(DomainError):
    http_status = 401
    code = "invalid_token"


class InvitationInvalid(DomainError):
    http_status = 410
    code = "invitation_invalid"


class InsufficientRole(DomainError):
    http_status = 403
    code = "insufficient_role"


class AIDisabled(DomainError):
    http_status = 403
    code = "ai_disabled"


class AgentDisabled(DomainError):
    http_status = 403
    code = "agent_disabled"


class HierarchyViolation(DomainError):
    http_status = 422
    code = "hierarchy_violation"


class InvalidTransition(DomainError):
    http_status = 422
    code = "invalid_transition"


class InvalidWorkflowConfig(DomainError):
    http_status = 422
    code = "invalid_workflow_config"


class ConfigInUse(DomainError):
    http_status = 409
    code = "config_in_use"


class DuplicateKey(DomainError):
    http_status = 409
    code = "duplicate_key"


class InvalidRank(DomainError):
    http_status = 422
    code = "invalid_rank"


class CycleDetected(DomainError):
    http_status = 422
    code = "link_cycle_detected"


class CannotProduceArtifact(DomainError):
    http_status = 422
    code = "role_artifact_mismatch"


class RejectRequiresReason(DomainError):
    http_status = 422
    code = "reason_required"


class GateNotApproved(DomainError):
    http_status = 409
    code = "gate_not_approved"


class VersionConflict(DomainError):
    http_status = 409
    code = "version_conflict"


class PrereqNotApproved(DomainError):
    http_status = 409
    code = "prereq_missing"


class TooManyInFlight(DomainError):
    http_status = 429
    code = "job_concurrency_limit"


# ---- Registration -------------------------------------------------------


def register_exception_handlers(app: FastAPI) -> None:
    """Attach one handler that renders any DomainError as JSON."""

    @app.exception_handler(DomainError)
    async def _handle(request: Request, exc: DomainError) -> JSONResponse:
        payload: dict[str, Any] = {"code": exc.code}
        if exc.message:
            payload["message"] = exc.message
        if exc.detail:
            payload["detail"] = exc.detail
        headers = {"Retry-After": "10"} if isinstance(exc, TooManyInFlight) else None
        return JSONResponse(status_code=exc.http_status, content=payload, headers=headers)
