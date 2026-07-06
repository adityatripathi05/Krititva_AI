# Contributing to Krititva AI

Thanks for your interest. This document covers the mechanics of contributing. For the design guardrails, read [`.claude/CLAUDE.md`](.claude/CLAUDE.md) first — it lists the ten non-negotiables (draft-and-review, provenance-before-LLM, immutability, 404-not-403, no phone-home, etc.).

## Ground rules

- **License:** AGPL-3.0-only. By contributing, you agree your work is licensed under AGPL-3.0.
- **DCO sign-off required.** Every commit must carry `Signed-off-by:`. See below.
- **Never `--no-verify`.** If a hook fails, fix the underlying issue.
- **Never bundle LLM weights.** Weights are pulled at runtime by the operator.
- **Never add phone-home.** With `KRITITVA_TELEMETRY_ENABLED=false` (the default), zero outbound requests must occur apart from user-initiated LLM calls.

## Developer Certificate of Origin (DCO)

Krititva uses the [Developer Certificate of Origin](https://developercertificate.org/) instead of a CLA. Add the sign-off line to every commit:

```bash
git commit -s -m "feat(work-items): enforce hard gates (M2.T4.4, FR-4.7.4)"
```

This appends:

```
Signed-off-by: Your Name <you@example.com>
```

CI enforces it via `.github/workflows/dco.yml`. If a commit is missing sign-off, amend it (`git commit -s --amend --no-edit`) and force-push to *your* branch (never to `main`).

## Setup

Prerequisites: Node 20.11+ with pnpm 9+, Python 3.12 with [uv](https://docs.astral.sh/uv/), Docker Engine 24+.

```bash
git clone <fork-url>
cd Krititva_AI
pnpm install
uv sync --project apps/api --extra dev

# Data plane
docker compose --file deploy/docker-compose.yml up postgres redis litellm -d

# Backend (in one shell)
uv run --project apps/api uvicorn app.main:app --reload

# Frontend (in another shell)
pnpm --filter @krititva/web dev
```

## Working on a change

1. **Find the roadmap task.** Every change should correspond to a task in [`docs/krititva-roadmap.md`](docs/krititva-roadmap.md) (e.g. `M0.T3.4`). If it doesn't, open an issue first to discuss whether it belongs.
2. **Read the SRS anchors** the task cites (`FR-4.1.4`, `NFR-5.2.1`, ...) in [`docs/krititva-srs.md`](docs/krititva-srs.md).
3. **Read the LLD section** the task cites in [`docs/krititva-lld.md`](docs/krititva-lld.md).
4. **Branch off `main`.** Naming: `feat/<M-task-id>-<slug>` or `fix/<M-task-id>-<slug>`.
5. **Write code + tests.**
6. **Update the LLD in the same PR** if your work changes the schema or a service contract.
7. **Verify locally**:
   ```bash
   uv run --project apps/api ruff check app tests
   uv run --project apps/api ruff format --check app tests
   uv run --project apps/api mypy app
   uv run --project apps/api pytest
   pnpm --filter @krititva/web lint typecheck
   ```

## Commit messages

Conventional-style prefix + roadmap task ID + primary anchor(s):

```
feat(work-items): enforce hard gates (M2.T4.4, FR-4.7.4)

Body explains WHY the change. No PR-scoped references
in code comments — they belong here in the message.

Signed-off-by: Aditya Tripathi <aditya.tripathi@echelonedge.com>
```

Prefixes: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`.

## Pull requests

Use the PR template. It captures the roadmap task, anchors implemented, and any LLD deltas. Draft PRs are welcome for early feedback.

CI must be green before merge:
- `backend` — ruff, ruff format, mypy strict, pytest
- `frontend` — lint, typecheck, build
- `traceability` — no orphan anchors
- `license-audit` — deps AGPL-compatible
- `dco` — every commit signed off

## Adding a dependency

**Python:** `uv add <package> --project apps/api`. The `license-audit` job blocks packages under non-AGPL-compatible licenses. If a needed package is blocked, discuss on the tracking issue before opening the PR.

**JavaScript:** `pnpm --filter @krititva/web add <package>`. Same license constraint.

Never add cloud-specific SDKs to `apps/api` core; storage adapters live behind an interface with the filesystem impl as default.

## Adding an AI agent (plugin)

Use the [`krititva-role-profile`](.claude/skills/krititva-role-profile/SKILL.md) skill as a guide. Plugins register via the `krititva.agents` entry-point group and can live in a separate package.

## Filing issues

- **Bugs:** include reproduction steps, expected vs actual, logs, and the `M<n>.T<x>` context.
- **Features:** motivate with a user story and cite the SRS anchor(s) the request maps to. If none fit, propose the SRS delta first.
- **Security:** DO NOT open a public issue. See [`SECURITY.md`](SECURITY.md).

## Communication

- GitHub Discussions for design conversations.
- Issues for concrete work.
- Public chat channels announced on release.
