/**
 * Project methodology + settings shapes, mirroring the backend contracts in
 * `apps/api/app/schemas/{project,methodology,llm_config}.py`.
 *
 * The `loadProjectSettings` fetch is a placeholder that returns the seeded Agile
 * template so the settings route renders before auth (M0.T6) and the generated
 * api-client (M1.T3) land. Swap the body for a TanStack Query call against
 * `GET /projects/{id}` + `/workflow/*` once those are wired — the types stay.
 */

export type Methodology = "agile" | "waterfall" | "hybrid";
export type WorkflowCategory = "todo" | "in_progress" | "done";
export type ProjectRole =
  | "project_owner"
  | "scrum_master"
  | "developer"
  | "qa"
  | "viewer"
  | "client_approver";
export type WorkItemKind =
  | "phase"
  | "epic"
  | "feature"
  | "story"
  | "task"
  | "bug"
  | "deliverable"
  | "test_case";

export interface WorkflowState {
  readonly key: string;
  readonly label: string;
  readonly category: WorkflowCategory;
  readonly sortOrder: number;
}

export interface WorkflowTransition {
  readonly fromKey: string;
  readonly toKey: string;
  readonly isHardGate: boolean;
  readonly requiredRole: ProjectRole | null;
  readonly approvalQuorum: Readonly<Record<string, number>>;
}

export interface HierarchyRule {
  readonly parentKind: WorkItemKind;
  readonly childKind: WorkItemKind;
}

export interface LlmConfig {
  readonly retrievalModel: string;
  readonly generationModels: Readonly<Record<"frontier" | "mid" | "fast", string>>;
  readonly disabledAgents: readonly string[];
  readonly techConstraints: string | null;
}

export interface ProjectSettings {
  readonly id: string;
  readonly key: string;
  readonly name: string;
  readonly methodology: Methodology;
  readonly aiEnabled: boolean;
  readonly states: readonly WorkflowState[];
  readonly transitions: readonly WorkflowTransition[];
  readonly hierarchy: readonly HierarchyRule[];
  readonly llmConfig: LlmConfig;
}

const PLACEHOLDER_AGILE: ProjectSettings = {
  id: "00000000-0000-0000-0000-000000000000",
  key: "DEMO",
  name: "Demo Project",
  methodology: "agile",
  aiEnabled: true,
  states: [
    { key: "backlog", label: "Backlog", category: "todo", sortOrder: 0 },
    { key: "in_progress", label: "In Progress", category: "in_progress", sortOrder: 10 },
    { key: "in_review", label: "In Review", category: "in_progress", sortOrder: 20 },
    { key: "qa", label: "QA", category: "in_progress", sortOrder: 30 },
    { key: "blocked", label: "Blocked", category: "in_progress", sortOrder: 40 },
    { key: "done", label: "Done", category: "done", sortOrder: 50 },
  ],
  transitions: [
    { fromKey: "backlog", toKey: "in_progress", isHardGate: false, requiredRole: null, approvalQuorum: {} },
    { fromKey: "in_progress", toKey: "in_review", isHardGate: false, requiredRole: null, approvalQuorum: {} },
    { fromKey: "in_review", toKey: "qa", isHardGate: false, requiredRole: null, approvalQuorum: {} },
    { fromKey: "qa", toKey: "done", isHardGate: false, requiredRole: "qa", approvalQuorum: {} },
  ],
  hierarchy: [
    { parentKind: "epic", childKind: "feature" },
    { parentKind: "feature", childKind: "story" },
    { parentKind: "story", childKind: "task" },
    { parentKind: "story", childKind: "bug" },
    { parentKind: "story", childKind: "test_case" },
  ],
  llmConfig: {
    retrievalModel: "nomic-embed-text-v1.5",
    generationModels: {
      frontier: "ollama/qwen2.5:32b-instruct",
      mid: "ollama/qwen2.5:7b-instruct",
      fast: "ollama/llama3.2:3b-instruct",
    },
    disabledAgents: [],
    techConstraints: null,
  },
};

export async function loadProjectSettings(projectId: string): Promise<ProjectSettings> {
  // TODO(M0.T6/M1.T3): replace with an authenticated api-client call.
  return Promise.resolve({ ...PLACEHOLDER_AGILE, id: projectId });
}

export function categoryVariant(category: WorkflowCategory): "secondary" | "outline" | "default" {
  switch (category) {
    case "todo":
      return "outline";
    case "in_progress":
      return "secondary";
    case "done":
      return "default";
  }
}
