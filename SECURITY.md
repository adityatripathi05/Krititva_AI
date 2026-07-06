# Security Policy

## Reporting a vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Email `security@krititva.dev` (or, until that alias is stood up: **aditya.tripathi@echelonedge.com** with subject `SECURITY: <short description>`). Encrypt with the maintainer's PGP key if available.

Include:
- A concise description of the issue.
- Reproduction steps or a proof-of-concept.
- Affected version(s) and configuration.
- Impact assessment (data exposure, privilege escalation, DoS, etc.).
- Your name / handle for credit (optional).

We aim to:
- Acknowledge within 72 hours.
- Provide an initial assessment within 7 days.
- Ship a fix or mitigation within 30 days for high/critical issues.

## Supported versions

Pre-alpha: only `main` receives security fixes. Once v1.0 releases, the latest minor line is supported.

## Scope

In scope:
- Authentication, RBAC, session, CSRF handling
- AI subsystem: prompt injection surfaces, provenance leakage, output-schema bypass
- Data at rest: LLM keys, SSO secrets, embeddings
- Docker Compose stack: default configuration and container escapes
- Signed link surface (`/public/signed/{token}`)

Out of scope for reports (but do tell us):
- Findings requiring physical access to a self-hosted install.
- DoS via crafted prompts on user-provided LLM endpoints — this is a capacity issue, not a Krititva bug.
- Social-engineering the operator.

## Disclosure

We prefer coordinated disclosure. When a fix ships, we credit reporters (unless they opt out) in the release notes.

## Non-negotiable security posture (for reference)

- Zero external requests by default (`KRITITVA_TELEMETRY_ENABLED=false`).
- No LLM output field is trusted — all outputs go through Pydantic schema validation with unknown-field drop.
- Draft-and-review enforced end to end: no AI output mutates canonical state without an audited human accept.
- Membership disclosure suppressed: unauthorized reads return 404, not 403.
- LLM provider keys and IdP secrets encrypted at rest with `KRITITVA_DATA_KEY`.

See [`.claude/CLAUDE.md`](.claude/CLAUDE.md) §1 and §10 for the full list.
