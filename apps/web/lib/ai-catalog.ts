import type { AgentRole, ArtifactType, ProjectRole } from "@/lib/api/types";

/**
 * The agent/artifact combinations that have a working generator today (M1). The
 * backend `ROLE_ARTIFACTS` graph is broader, but the un-listed artifacts
 * (epic/story/task breakdowns, sprint/api contracts) land with their M2/M3 role
 * profiles; offering them here would only yield an `unsupported_artifact` error.
 */
export interface GeneratableArtifact {
  readonly agent: AgentRole;
  readonly artifact: ArtifactType;
  readonly label: string;
  readonly needsFocusStory?: boolean;
}

export const GENERATABLE: readonly GeneratableArtifact[] = [
  { agent: "project_owner", artifact: "srs", label: "SRS document" },
  { agent: "architect", artifact: "hld", label: "High-level design (HLD)" },
  { agent: "architect", artifact: "lld", label: "Low-level design (LLD)" },
  { agent: "qa", artifact: "test_plan", label: "Test plan" },
  {
    agent: "qa",
    artifact: "test_cases",
    label: "Test cases (for a story)",
    needsFocusStory: true,
  },
];

// Mirrors app/ai/catalog.py `_AGENT_INVOCATION`: which project role may invoke
// which agent. viewer / client_approver may invoke none.
const AGENT_INVOCATION: Record<ProjectRole, readonly AgentRole[]> = {
  project_owner: ["project_owner", "architect", "scrum_master", "developer", "qa"],
  scrum_master: ["scrum_master", "developer", "qa"],
  developer: ["developer", "qa"],
  qa: ["qa"],
  viewer: [],
  client_approver: [],
};

export function mayInvoke(role: ProjectRole | null, agent: AgentRole): boolean {
  return role !== null && AGENT_INVOCATION[role].includes(agent);
}

/** The generatable artifacts the caller's project role is allowed to invoke. */
export function invocableArtifacts(
  role: ProjectRole | null,
): readonly GeneratableArtifact[] {
  return GENERATABLE.filter((g) => mayInvoke(role, g.agent));
}
