"""Token-budget packing + overflow fallback (M1.T4.2/T4.5/T4.6).

Pure-function tests — the packing invariants the assembler relies on, pinned with
Hypothesis, plus the lineage summarization fallback.
"""

from __future__ import annotations

import uuid

from hypothesis import given
from hypothesis import strategies as st

from app.ai.context import ContextChunk, pack_to_budget, summarize_lineage_fallback

_TOKENS = st.lists(st.integers(min_value=1, max_value=500), max_size=15)


def _chunks(stage: str, tokens: list[int]) -> list[ContextChunk]:
    return [
        ContextChunk(stage=stage, content="x", token_count=t, chunk_id=uuid.uuid4()) for t in tokens
    ]


@given(_TOKENS, _TOKENS, _TOKENS, st.integers(min_value=0, max_value=3000))
def test_pack_never_exceeds_budget(
    lineage: list[int], semantic: list[int], operational: list[int], budget: int
) -> None:
    packed = pack_to_budget(
        _chunks("lineage", lineage),
        _chunks("semantic", semantic),
        _chunks("operational", operational),
        budget,
    )
    assert packed.total_tokens <= budget
    assert packed.total_tokens == sum(c.token_count for c in packed.all_chunks())


@given(_TOKENS, _TOKENS, _TOKENS, st.integers(min_value=0, max_value=3000))
def test_pack_preserves_within_stage_order(
    lineage: list[int], semantic: list[int], operational: list[int], budget: int
) -> None:
    la, se, op = (
        _chunks("lineage", lineage),
        _chunks("semantic", semantic),
        _chunks("operational", operational),
    )
    packed = pack_to_budget(la, se, op, budget)
    for original, kept in ((la, packed.lineage), (se, packed.semantic), (op, packed.operational)):
        ids = [c.chunk_id for c in original]
        kept_ids = [c.chunk_id for c in kept]
        # kept is a subsequence of the original order
        it = iter(ids)
        assert all(any(k == o for o in it) for k in kept_ids)


def test_pack_prioritizes_lineage() -> None:
    # Budget fits exactly one 100-token chunk; lineage wins over semantic.
    packed = pack_to_budget(_chunks("lineage", [100]), _chunks("semantic", [100]), [], budget=100)
    assert len(packed.lineage) == 1
    assert packed.semantic == []


async def test_summarize_folds_deepest_lineage() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    lineage = [
        ContextChunk(stage="lineage", content="A", token_count=100, chunk_id=a, depth=0),
        ContextChunk(stage="lineage", content="B", token_count=100, chunk_id=b, depth=1),
        ContextChunk(stage="lineage", content="C", token_count=100, chunk_id=c, depth=2),
    ]

    async def summarizer(texts: list[str]) -> str:
        return "SUMMARY of " + " ".join(texts)

    out = await summarize_lineage_fallback(lineage, budget=300, summarizer=summarizer)
    # half=150 → keep depth 0 (100), fold depths 1 and 2 into one summary node.
    assert len(out) == 2
    assert out[0].chunk_id == a
    assert out[1].summarized_from == (b, c)
    assert "SUMMARY" in out[1].content


async def test_summarize_noop_when_all_fit() -> None:
    x = uuid.uuid4()
    lineage = [ContextChunk(stage="lineage", content="X", token_count=10, chunk_id=x, depth=0)]

    async def summarizer(texts: list[str]) -> str:  # pragma: no cover - not reached
        return "unused"

    out = await summarize_lineage_fallback(lineage, budget=1000, summarizer=summarizer)
    assert out == lineage
