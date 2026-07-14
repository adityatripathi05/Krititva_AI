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
    retry_after: int | None = None  # seconds; emitted as a Retry-After header

    def __init__(
        self,
        message: str = "",
        detail: dict[str, Any] | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}
        if retry_after is not None:
            self.retry_after = retry_after


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


class AlreadyBootstrapped(DomainError):
    http_status = 409
    code = "already_bootstrapped"


class EmailAlreadyRegistered(DomainError):
    http_status = 409
    code = "email_already_registered"


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


class InvalidReference(DomainError):
    http_status = 422
    code = "invalid_reference"


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


class InvalidDocumentState(DomainError):
    http_status = 422
    code = "invalid_document_state"


class PrereqNotApproved(DomainError):
    http_status = 409
    code = "prereq_missing"


class TooManyInFlight(DomainError):
    http_status = 429
    code = "job_concurrency_limit"
    retry_after = 10


class RateLimited(DomainError):
    http_status = 429
    code = "rate_limited"


class InvalidJobState(DomainError):
    http_status = 409
    code = "invalid_job_state"


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
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after is not None else None
        return JSONResponse(status_code=exc.http_status, content=payload, headers=headers)
