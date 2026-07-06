# @krititva/methodology-templates

Seed JSON for the three methodology profiles Krititva ships. Applied atomically to `workflow_states`, `workflow_transitions`, and `hierarchy_rules` on project creation (see [`docs/krititva-srs.md`](../../docs/krititva-srs.md) FR-4.3 and [`docs/krititva-lld.md`](../../docs/krititva-lld.md) §2.2).

## Templates

- [`agile.json`](agile.json) — Epic → Feature → Story → Task. States: backlog → in_progress → in_review → qa → done, plus `blocked`. No hard gates by default.
- [`waterfall.json`](waterfall.json) — Phase → Deliverable → Task. States: not_started → in_progress → gate_review → done. `gate_review → done` is a hard gate; approval quorum defaults to `project_owner + client_approver` (customizable per project post-creation).
- [`hybrid.json`](hybrid.json) — Phase → Epic → Feature → Story → Task. Phase-level hard gates; sprint-level flow inside each phase.

## Schema

`schema.json` is the JSON Schema that the backend validates every template against before applying it. Editing a template? Validate:

```bash
pnpm dlx ajv-cli validate -s packages/methodology-templates/schema.json -d "packages/methodology-templates/{agile,waterfall,hybrid}.json"
```

## Rules

- Methodology-as-data is a load-bearing invariant. Never encode Agile-vs-Waterfall behavior in service code — express it here. See [`.claude/CLAUDE.md`](../../.claude/CLAUDE.md) §1.8.
- A quorum spec in a transition uses the `project_role` keys defined in `docs/krititva-lld.md` §2.2.
- `is_hard_gate=true` transitions must have a non-empty `approval_quorum`.
