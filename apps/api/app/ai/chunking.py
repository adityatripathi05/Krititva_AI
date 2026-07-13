"""Section-aware markdown chunker (FR-4.5.4).

Splits a document version's markdown into retrieval chunks at H1-H4 headings.
Each chunk carries a ``section_path`` breadcrumb (the heading hierarchy that
contains it), a SHA-256 ``content_hash``, and an estimated ``token_count``.

Token counting is a deterministic **offline** estimate — real BPE counting via
tiktoken is avoided because tiktoken downloads its vocabulary from the network on
first use, which would violate the zero-phone-home default (§CLAUDE.md §1.6). The
estimate is a word/punctuation token count, which tracks BPE counts closely
enough for chunk-packing budgets (§HLD 5.4) without any external call.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

# H1-H4 only. H5/H6 stay inside their parent section's body (they are not split
# boundaries). Allow optional closing hashes (``## Title ##``).
_HEADING = re.compile(r"^(#{1,4})[ \t]+(\S.*?)[ \t]*#*[ \t]*$")
_TOKEN = re.compile(r"\w+|[^\w\s]")

# Delimiter between heading titles in a section_path breadcrumb.
SECTION_SEP = " / "


@dataclass(frozen=True)
class ChunkSpec:
    """A prepared chunk, ready to persist as a ``document_chunks`` row."""

    section_path: str
    content: str
    content_hash: str
    token_count: int


def estimate_tokens(text: str) -> int:
    """Offline token estimate (word + punctuation tokens). Always ≥ 1 for
    non-empty input; see the module docstring for why this is not tiktoken."""
    return len(_TOKEN.findall(text))


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _finalize(section_path: str, lines: list[str]) -> ChunkSpec | None:
    content = "\n".join(lines).strip()
    if not content:
        return None
    return ChunkSpec(
        section_path=section_path,
        content=content,
        content_hash=_content_hash(content),
        token_count=estimate_tokens(content),
    )


def chunk_markdown(content_md: str) -> list[ChunkSpec]:
    """Chunk ``content_md`` at H1-H4 headings.

    Each heading opens a new chunk consisting of the heading line plus the body
    up to the next H1-H4 heading. Content before the first heading (if any) is
    emitted as a preamble chunk with an empty ``section_path``. Whitespace-only
    sections are dropped.
    """
    chunks: list[ChunkSpec] = []
    stack: list[tuple[int, str]] = []
    current_path = ""
    current_lines: list[str] = []

    for line in content_md.splitlines():
        match = _HEADING.match(line)
        if match is None:
            current_lines.append(line)
            continue
        spec = _finalize(current_path, current_lines)
        if spec is not None:
            chunks.append(spec)
        level = len(match.group(1))
        title = match.group(2).strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        current_path = SECTION_SEP.join(t for _, t in stack)
        current_lines = [line]

    spec = _finalize(current_path, current_lines)
    if spec is not None:
        chunks.append(spec)
    return chunks
