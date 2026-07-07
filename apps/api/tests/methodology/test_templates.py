"""Unit tests for the methodology template loader (FR-4.3.1, FR-4.3.3-4.3.5).

Pure — reads the seed JSON, no Postgres needed.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.methodology import MethodologyTemplate, load_template
from app.methodology.templates import _DEFAULT_DIR
from app.models.enums import Methodology, WorkItemKind


@pytest.mark.parametrize("methodology", list(Methodology))
def test_every_methodology_template_loads(methodology: Methodology) -> None:
    template = load_template(methodology)
    assert template.methodology is methodology
    assert template.states
    assert template.transitions
    assert template.hierarchy


def test_all_three_seed_files_present() -> None:
    for m in Methodology:
        assert (_DEFAULT_DIR / f"{m.value}.json").is_file()


def test_agile_hierarchy_and_states() -> None:
    """FR-4.3.3: epic→feature→story→task, bug sibling of story, agile states."""
    t = load_template(Methodology.agile)
    pairs = {(h.parent_kind, h.child_kind) for h in t.hierarchy}
    assert (WorkItemKind.epic, WorkItemKind.feature) in pairs
    assert (WorkItemKind.feature, WorkItemKind.story) in pairs
    assert (WorkItemKind.story, WorkItemKind.task) in pairs
    assert (WorkItemKind.story, WorkItemKind.bug) in pairs
    keys = {s.key for s in t.states}
    assert {"backlog", "in_progress", "in_review", "qa", "done"} <= keys
    assert not any(tr.is_hard_gate for tr in t.transitions)


def test_waterfall_has_hard_gate_to_done() -> None:
    """FR-4.3.4: phase→deliverable→task, gate_review→done is a hard gate."""
    t = load_template(Methodology.waterfall)
    gate = [tr for tr in t.transitions if tr.is_hard_gate]
    assert len(gate) == 1
    assert gate[0].to_key == "done"
    assert gate[0].approval_quorum  # non-empty quorum on the gate
    pairs = {(h.parent_kind, h.child_kind) for h in t.hierarchy}
    assert (WorkItemKind.phase, WorkItemKind.deliverable) in pairs


def test_hybrid_phase_wraps_epics_and_gates() -> None:
    """FR-4.3.5: phase may contain epics; a gate exists out of gate_review."""
    t = load_template(Methodology.hybrid)
    pairs = {(h.parent_kind, h.child_kind) for h in t.hierarchy}
    assert (WorkItemKind.phase, WorkItemKind.epic) in pairs
    assert any(tr.is_hard_gate for tr in t.transitions)


def test_transition_to_unknown_state_rejected() -> None:
    with pytest.raises(ValidationError):
        MethodologyTemplate.model_validate(
            {
                "methodology": "agile",
                "states": [{"key": "a", "label": "A", "category": "todo", "sort_order": 0}],
                "transitions": [{"from": "a", "to": "ghost"}],
                "hierarchy": [],
            }
        )


def test_hard_gate_without_quorum_rejected() -> None:
    with pytest.raises(ValidationError):
        MethodologyTemplate.model_validate(
            {
                "methodology": "waterfall",
                "states": [
                    {"key": "a", "label": "A", "category": "in_progress", "sort_order": 0},
                    {"key": "b", "label": "B", "category": "done", "sort_order": 1},
                ],
                "transitions": [{"from": "a", "to": "b", "is_hard_gate": True}],
                "hierarchy": [],
            }
        )


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        MethodologyTemplate.model_validate(
            {
                "methodology": "agile",
                "states": [{"key": "a", "label": "A", "category": "todo", "sort_order": 0}],
                "transitions": [],
                "hierarchy": [],
                "surprise": 1,
            }
        )
