"""LLM client wrapper (LLD §5.6, NFR-5.2.6).

All model calls go through :class:`LLMClient`, which enforces structured output:
the raw completion is parsed with ``response_format.model_validate_json`` and
**unknown fields are dropped** (§CLAUDE.md §1.10) — no field an LLM emits may
reach account/config state. Tests use :class:`FakeLLMClient`; real Ollama runs
only in the tagged-release smoke suite (§CLAUDE.md §5).
"""

from __future__ import annotations

from typing import Any, Protocol, TypedDict

from pydantic import BaseModel, ValidationError

_MAX_ATTEMPTS = 2


class Msg(TypedDict):
    role: str
    content: str


class LLMError(RuntimeError):
    """Model call failed or its output could not be validated after retries."""


class LLMTimeout(LLMError):
    """Model call exceeded the timeout budget."""


class GenerationOutput(BaseModel):
    """Structured output for document-producing artifacts (SRS/HLD/LLD/test_plan).

    ``extra='ignore'`` implements the §1.10 drop-unknown-fields rule — the model
    cannot smuggle extra keys into persisted state."""

    model_config = {"extra": "ignore"}

    title: str
    body_md: str


class LLMResult(BaseModel):
    """Validated model output plus accounting metadata."""

    model_config = {"arbitrary_types_allowed": True}

    artifact: BaseModel
    model: str
    prompt_tokens: int
    output_tokens: int


class LLMClientProtocol(Protocol):
    async def acompletion(
        self,
        *,
        model: str,
        messages: list[Msg],
        response_format: type[BaseModel],
        metadata: dict[str, Any],
        timeout_s: int = 300,
    ) -> LLMResult: ...


class LLMClient:
    """Wraps ``litellm.acompletion`` with schema-strict parsing + one reprompt."""

    async def acompletion(
        self,
        *,
        model: str,
        messages: list[Msg],
        response_format: type[BaseModel],
        metadata: dict[str, Any],
        timeout_s: int = 300,
    ) -> LLMResult:
        import litellm

        convo: list[Msg] = list(messages)
        last_error: Exception | None = None
        for _ in range(_MAX_ATTEMPTS):
            try:
                resp = await litellm.acompletion(
                    model=model,
                    messages=convo,
                    response_format=response_format,
                    metadata=metadata,
                    timeout=timeout_s,
                )
            except litellm.Timeout as exc:  # type: ignore[attr-defined]
                raise LLMTimeout(str(exc)) from exc
            except Exception as exc:  # provider/transport error
                raise LLMError(str(exc)) from exc

            content = resp.choices[0].message.content or ""
            try:
                artifact = response_format.model_validate_json(content)
            except ValidationError as exc:
                last_error = exc
                convo.append({"role": "assistant", "content": content})
                convo.append(
                    {
                        "role": "user",
                        "content": f"Your JSON was invalid: {exc}. Re-emit valid JSON.",
                    }
                )
                continue
            usage = getattr(resp, "usage", None)
            return LLMResult(
                artifact=artifact,
                model=getattr(resp, "model", model),
                prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            )
        raise LLMError(f"structured output invalid after {_MAX_ATTEMPTS} attempts: {last_error}")


class FakeLLMClient:
    """Deterministic client for tests — validates a canned payload against the
    requested schema so it exercises the same structured-output path."""

    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self._payload = payload

    async def acompletion(
        self,
        *,
        model: str,
        messages: list[Msg],
        response_format: type[BaseModel],
        metadata: dict[str, Any],
        timeout_s: int = 300,
    ) -> LLMResult:
        payload = self._payload if self._payload is not None else _default_payload(response_format)
        artifact = response_format.model_validate(payload)
        return LLMResult(artifact=artifact, model="fake/echo", prompt_tokens=11, output_tokens=22)


def _default_payload(response_format: type[BaseModel]) -> dict[str, Any]:
    if issubclass(response_format, GenerationOutput):
        return {"title": "Generated Draft", "body_md": "# Generated Draft\n\nDraft body."}
    return {}
