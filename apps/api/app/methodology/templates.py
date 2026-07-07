"""Load + validate the seed methodology templates (FR-4.3.1).

The JSON under ``packages/methodology-templates/`` is the source of truth for the
Agile / Waterfall / Hybrid workflows. It is authored against ``schema.json`` and
re-validated here at load time by parsing into Pydantic models — structural
validation plus referential checks (transitions point at real states; hard gates
carry an approval quorum). We deliberately do not pull in a runtime ``jsonschema``
dependency: Pydantic already gives us strict, unknown-field-rejecting parsing.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import get_settings
from app.models.enums import Methodology, ProjectRole, WorkflowCategory, WorkItemKind

# apps/api/app/methodology/templates.py → parents[4] == repo root.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_DIR = _REPO_ROOT / "packages" / "methodology-templates"


class TemplateState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    category: WorkflowCategory
    sort_order: int = Field(ge=0)


class TemplateTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_key: str = Field(alias="from")
    to_key: str = Field(alias="to")
    required_role: ProjectRole | None = None
    is_hard_gate: bool = False
    approval_quorum: dict[str, int] = Field(default_factory=dict)


class TemplateHierarchy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_kind: WorkItemKind
    child_kind: WorkItemKind


class MethodologyTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    methodology: Methodology
    description: str | None = None
    states: list[TemplateState] = Field(min_length=1)
    transitions: list[TemplateTransition]
    hierarchy: list[TemplateHierarchy]

    @model_validator(mode="after")
    def _check_referential_integrity(self) -> MethodologyTemplate:
        keys = {s.key for s in self.states}
        if len(keys) != len(self.states):
            raise ValueError("duplicate state keys in template")
        for t in self.transitions:
            if t.from_key not in keys:
                raise ValueError(f"transition from unknown state '{t.from_key}'")
            if t.to_key not in keys:
                raise ValueError(f"transition to unknown state '{t.to_key}'")
            if t.is_hard_gate and not t.approval_quorum:
                raise ValueError(
                    f"hard-gate transition {t.from_key}->{t.to_key} needs an approval_quorum"
                )
            for role in t.approval_quorum:
                if role not in ProjectRole.__members__:
                    raise ValueError(f"approval_quorum names unknown role '{role}'")
        return self


def _templates_dir() -> Path:
    configured = get_settings().methodology_templates_dir
    return Path(configured) if configured else _DEFAULT_DIR


@lru_cache(maxsize=len(Methodology))
def load_template(methodology: Methodology) -> MethodologyTemplate:
    """Load and validate the seed template for ``methodology``.

    Cached per methodology — the seed files are read-only at runtime.
    """
    path = _templates_dir() / f"{methodology.value}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    template = MethodologyTemplate.model_validate(data)
    if template.methodology is not methodology:
        raise ValueError(
            f"{path.name} declares methodology '{template.methodology.value}', "
            f"expected '{methodology.value}'"
        )
    return template
