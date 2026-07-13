"""Agent/artifact catalog — the data that governs what AI agents may produce.

Sourced from the blueprint (§6) and LLD §3.1. Kept as data (dicts/sets), never
branched in code (§CLAUDE.md §1.8 spirit): the orchestrator's authorization gates
read these tables. Role profiles (M1.T5/T6) plug their real prompts/schemas into
the generation worker; this module only encodes the *permission* graph and the
document target of document-producing artifacts.
"""

from __future__ import annotations

from app.models.enums import AgentRole, ArtifactType, DocType, ProjectRole

# Which agent role may produce which artifact (blueprint ROLE_ARTIFACTS).
ROLE_ARTIFACTS: dict[AgentRole, frozenset[ArtifactType]] = {
    AgentRole.project_owner: frozenset({ArtifactType.srs, ArtifactType.epic_breakdown}),
    AgentRole.architect: frozenset({ArtifactType.hld, ArtifactType.lld}),
    AgentRole.scrum_master: frozenset({ArtifactType.sprint_plan, ArtifactType.story_breakdown}),
    AgentRole.developer: frozenset({ArtifactType.task_breakdown, ArtifactType.api_contract}),
    AgentRole.qa: frozenset({ArtifactType.test_plan, ArtifactType.test_cases}),
}

# Upstream document types that must exist AND be approved before an artifact runs
# (blueprint ARTIFACT_PREREQS). Values are ``doc_type`` strings.
ARTIFACT_PREREQS: dict[ArtifactType, frozenset[str]] = {
    ArtifactType.hld: frozenset({"srs"}),
    ArtifactType.lld: frozenset({"srs", "hld"}),
    ArtifactType.test_plan: frozenset({"srs"}),
    ArtifactType.test_cases: frozenset({"srs"}),
}

# Which project role may invoke which agent role (mirrors deps.require_agent_permission;
# LLD §3.1 may_invoke_agent). project_owner may invoke any; scrum_master → SM/Dev/QA;
# developer → Dev/QA; qa → QA; viewer/client_approver → none.
_AGENT_INVOCATION: dict[ProjectRole, frozenset[AgentRole]] = {
    ProjectRole.project_owner: frozenset(AgentRole),
    ProjectRole.scrum_master: frozenset(
        {AgentRole.scrum_master, AgentRole.developer, AgentRole.qa}
    ),
    ProjectRole.developer: frozenset({AgentRole.developer, AgentRole.qa}),
    ProjectRole.qa: frozenset({AgentRole.qa}),
}

# Document-producing artifacts and their target doc_type. Work-item-producing
# artifacts (epic/story/task breakdowns, sprint plans) persist differently and
# land with their role profiles (M1.T5/T6); they are absent here on purpose.
ARTIFACT_DOC_TYPE: dict[ArtifactType, DocType] = {
    ArtifactType.srs: DocType.srs,
    ArtifactType.hld: DocType.hld,
    ArtifactType.lld: DocType.lld,
    ArtifactType.test_plan: DocType.test_plan,
}


def can_produce(agent_role: AgentRole, artifact: ArtifactType) -> bool:
    return artifact in ROLE_ARTIFACTS.get(agent_role, frozenset())


def may_invoke_agent(project_role: ProjectRole, agent_role: AgentRole) -> bool:
    return agent_role in _AGENT_INVOCATION.get(project_role, frozenset())


def prereq_doc_types(artifact: ArtifactType) -> frozenset[str]:
    return ARTIFACT_PREREQS.get(artifact, frozenset())
