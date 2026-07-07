"""Per-project LLM configuration (LLD §11 LLMConfig, FR-4.2.4).

Stored as JSONB in ``projects.llm_config``. ``disabled_agents`` is typed as
``list[str]`` in v1 — the concrete ``agent_role`` enum lands with the agent
matrix in M1.T3, at which point this tightens.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_Tier = Literal["frontier", "mid", "fast"]


def _default_generation_models() -> dict[_Tier, str]:
    return {
        "frontier": "ollama/qwen2.5:32b-instruct",
        "mid": "ollama/qwen2.5:7b-instruct",
        "fast": "ollama/llama3.2:3b-instruct",
    }


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retrieval_model: str = "nomic-embed-text-v1.5"
    generation_models: dict[_Tier, str] = Field(default_factory=_default_generation_models)
    disabled_agents: list[str] = Field(default_factory=list)
    tech_constraints: str | None = None
    provider_overrides: dict[str, str] = Field(default_factory=dict)
