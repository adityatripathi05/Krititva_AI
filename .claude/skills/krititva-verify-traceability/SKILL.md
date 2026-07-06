---
name: krititva-verify-traceability
description: Verify that new code, tests, or docs carry the SRS FR/NFR anchors they claim to implement, and that every FR/NFR in the SRS has at least one implementation reference. Use before opening a PR and as a CI check.
---

# krititva-verify-traceability

Enforces `OR-6.3.1` — every requirement in the SRS SHALL be linked to at least one Epic and at least one Test Case, and every implementation-scoped commit SHALL carry the anchor(s) it delivers.

## When to use
- Before opening or updating a PR (self-check).
- As part of `M0.T1.4` CI job (`traceability-check`).
- When auditing a milestone at completion.

## Inputs
- (optional) A commit or PR range. Default: uncommitted + staged changes.

## Steps

1. **Extract claimed anchors** from the change set:
   - PR title / commit message: match `FR-\d+\.\d+(\.\d+)?` and `NFR-\d+\.\d+(\.\d+)?`.
   - Code comments in the diff: match the same pattern.
   - Test file docstrings.
   - Result: a set `Claimed`.

2. **Extract the SRS master list** from `docs/krititva-srs.md`:
   - Every `**FR-...`, `**NFR-...`, and `**OR-...` bold anchor.
   - Result: a set `Universe`.

3. **Extract implemented anchors from source** by grepping the whole tree for the same regex:
   - `apps/api/app/**/*.py`
   - `apps/web/**/*.ts`, `*.tsx`
   - `apps/api/tests/**/*.py`
   - `docs/krititva-roadmap.md` (task→FR mapping)
   - Result: a set `Implemented`.

4. **Report three views:**
   - **Missing** = `Claimed - Implemented`. PR claims anchors it doesn't reference in code/tests. Blocker.
   - **Untraced** = `Universe - Implemented`. Requirements never referenced anywhere. Warn if new; block if the roadmap says the owning milestone is complete.
   - **Orphan** = `Implemented - Universe`. Anchor cited that doesn't exist in the SRS (typo or removed requirement). Blocker.

## Commands (bash)

Use these directly; they compose the extraction and diff.

```bash
# Universe (from SRS)
grep -oE '(FR|NFR|OR)-[0-9]+(\.[0-9]+){1,2}' docs/krititva-srs.md | sort -u > /tmp/kt-universe

# Implemented (across code + tests + roadmap)
grep -orhE '(FR|NFR|OR)-[0-9]+(\.[0-9]+){1,2}' \
  apps/api/app apps/api/tests apps/web docs/krititva-roadmap.md 2>/dev/null | sort -u > /tmp/kt-implemented

# Claimed (staged + committed on this branch)
git diff --unified=0 origin/main...HEAD -- apps docs \
  | grep -oE '(FR|NFR|OR)-[0-9]+(\.[0-9]+){1,2}' | sort -u > /tmp/kt-claimed

comm -23 /tmp/kt-claimed /tmp/kt-implemented    # Missing
comm -23 /tmp/kt-universe /tmp/kt-implemented   # Untraced
comm -23 /tmp/kt-implemented /tmp/kt-universe   # Orphan
```

## Output format

Report as three sections in this exact order (blocker first):

```
BLOCKERS
- Missing: FR-4.6.4 was claimed in the PR title but does not appear in any file changed.
- Orphan:  NFR-5.2.99 appears in apps/api/app/services/auth.py but is not defined in the SRS.

WARNINGS
- Untraced: FR-4.8.4 has no references. Owning milestone: M3 (not yet complete).
```

## Interpretation guide

- **Missing** — either fix the code/tests to include the anchor, or remove the claim from the PR title/body.
- **Orphan** — either the anchor is a typo (fix), or the SRS was updated and left references stale (update the SRS in the same PR).
- **Untraced** — acceptable while the owning milestone is in progress. Blocker only if the milestone is marked done in `docs/krititva-roadmap.md`.

## Don't

- Don't relax the regex to be case-insensitive; the anchors are `FR-4.6.4`, not `fr-4.6.4`.
- Don't count matches inside `.md` files as implementation — the SRS/HLD/LLD cite themselves. Only code and test files count as "implemented".
- Don't add anchor-noise comments to satisfy the check. Anchors belong on the specific code that satisfies the requirement, not scattered as decorators.
