"""Chunker unit + property tests (M1.T2.2, FR-4.5.4).

Pure-function tests — no DB, no network. Property tests (Hypothesis) pin the
invariants the retrieval pipeline relies on: every H1-H4 heading lands in exactly
one chunk, breadcrumbs nest correctly, and hashing/token counts are deterministic.
"""

from __future__ import annotations

import re

from hypothesis import given
from hypothesis import strategies as st

from app.ai.chunking import (
    SECTION_SEP,
    ChunkSpec,
    chunk_markdown,
    estimate_tokens,
)

_HEADING = re.compile(r"^(#{1,4})[ \t]+\S")


def test_splits_on_headings_and_builds_breadcrumb() -> None:
    md = """\
# System SRS
Intro line.
## Auth
Auth body.
### Login
Login body.
## Reporting
Reporting body.
"""
    chunks = chunk_markdown(md)
    paths = [c.section_path for c in chunks]
    assert paths == [
        "System SRS",
        "System SRS / Auth",
        "System SRS / Auth / Login",
        "System SRS / Reporting",
    ]


def test_preamble_before_first_heading_is_its_own_chunk() -> None:
    md = "Loose intro text.\n\n# Title\nBody."
    chunks = chunk_markdown(md)
    assert chunks[0].section_path == ""
    assert "Loose intro" in chunks[0].content
    assert chunks[1].section_path == "Title"


def test_h5_h6_are_not_split_boundaries() -> None:
    md = "# Top\nbody\n##### deep\nstill top section\n"
    chunks = chunk_markdown(md)
    assert len(chunks) == 1
    assert "##### deep" in chunks[0].content


def test_sibling_heading_pops_stack() -> None:
    md = "# A\n## B\ntext\n# C\ntext"
    paths = [c.section_path for c in chunk_markdown(md)]
    assert paths == ["A", "A / B", "C"]


def test_whitespace_only_document_yields_no_chunks() -> None:
    assert chunk_markdown("   \n\n\t\n") == []


def test_content_hash_and_tokens_are_deterministic() -> None:
    md = "# H\nsome content here"
    a = chunk_markdown(md)
    b = chunk_markdown(md)
    assert a == b
    assert isinstance(a[0], ChunkSpec)


def test_estimate_tokens_positive_for_nonempty() -> None:
    assert estimate_tokens("hello world") >= 2
    assert estimate_tokens("") == 0


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

_LINE = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=40)
_DOC = st.lists(_LINE, max_size=30).map("\n".join)


@given(_DOC)
def test_every_heading_produces_exactly_one_chunk(md: str) -> None:
    heading_lines = [ln for ln in md.splitlines() if _HEADING.match(ln)]
    chunks = chunk_markdown(md)
    # Each heading chunk starts with its heading line; count heading-led chunks.
    heading_chunks = [c for c in chunks if _HEADING.match(c.content.splitlines()[0])]
    assert len(heading_chunks) == len(heading_lines)


@given(_DOC)
def test_all_chunks_have_hash_and_positive_tokens(md: str) -> None:
    for c in chunk_markdown(md):
        assert len(c.content_hash) == 64
        assert c.token_count >= 1
        assert c.content == c.content.strip()


@given(_DOC)
def test_breadcrumb_depth_never_exceeds_four(md: str) -> None:
    for c in chunk_markdown(md):
        if c.section_path:
            assert len(c.section_path.split(SECTION_SEP)) <= 4
