"""Jinja environment for prompt templates (``app/ai/prompts/*.j2``).

Autoescape is intentionally off: these render prompt text for an LLM, not HTML,
so HTML-escaping would corrupt the prompt. Untrusted document content is never
injected raw — it arrives already wrapped in delimited context blocks
(``AssembledContext.render``) with an instruction to ignore embedded commands.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_PROMPTS_DIR = Path(__file__).parent / "prompts"

_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=False,  # noqa: S701 — prompt text, not HTML; see module docstring
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)


def render_template(name: str, /, **context: object) -> str:
    return _env.get_template(name).render(**context)
