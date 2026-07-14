/**
 * API shapes mirroring the backend Pydantic schemas
 * (`apps/api/app/schemas/{project,methodology,work_item,auth}.py`).
 *
 * URLs in this app key projects by their UUID (`[projectId]`), not the human
 * `key`, because every backend endpoint is id-addressed and there is no
 * key→id lookup endpoint. The human key is shown in the UI, not the URL.
 */

export type Methodology = "agile" | "waterfall" | "hybrid";
export type PortalMode = "none" | "export_only" | "portal";
export type ProjectStatus = "active" | "on_hold" | "completed" | "cancelled";
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
export type LinkType = "derived_from" | "tests" | "blocks" | "relates_to";

export interface Project {
  readonly id: string;
  readonly organization_id: string | null;
  readonly client_id: string | null;
  readonly key: string;
  readonly name: string;
  readonly methodology: Methodology;
  readonly ai_enabled: boolean;
  readonly llm_config: Record<string, unknown>;
  readonly client_portal_mode: PortalMode;
  readonly start_date: string | null;
  readonly target_date: string | null;
  readonly status: ProjectStatus;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface WorkflowState {
  readonly id: string;
  readonly project_id: string;
  readonly key: string;
  readonly label: string;
  readonly category: WorkflowCategory;
  readonly sort_order: number;
}

export interface WorkflowTransition {
  readonly id: string;
  readonly project_id: string;
  readonly from_state: string;
  readonly to_state: string;
  readonly is_hard_gate: boolean;
  readonly required_role: ProjectRole | null;
  readonly approval_quorum: Record<string, number>;
}

export interface HierarchyRule {
  readonly parent_kind: WorkItemKind;
  readonly child_kind: WorkItemKind;
}

export interface WorkItem {
  readonly id: string;
  readonly project_id: string;
  readonly kind: WorkItemKind;
  readonly parent_id: string | null;
  readonly seq: number;
  readonly key: string;
  readonly title: string;
  readonly description_md: string;
  readonly acceptance_md: string | null;
  readonly state_id: string;
  readonly assignee_id: string | null;
  readonly sprint_id: string | null;
  readonly milestone_id: string | null;
  readonly story_points: number | null;
  readonly estimated_hours: number | null;
  readonly actual_hours: number | null;
  readonly rank: string | null;
  readonly ai_generated: boolean;
  readonly stale: boolean;
  readonly created_by: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface Membership {
  readonly project_id: string;
  readonly role: ProjectRole;
  readonly allocation_pct: number;
}

export interface CurrentUser {
  readonly user: {
    readonly id: string;
    readonly email: string;
    readonly display_name: string;
    readonly org_role: "org_admin" | "member";
    readonly organization_id: string | null;
  };
  readonly memberships: readonly Membership[];
}

export interface ApiError {
  readonly code: string;
  readonly message?: string;
  readonly detail?: Record<string, unknown>;
}

// --- AI artifacts (mirrors app/schemas/artifacts.py + app/schemas/document.py) ---

export type AgentRole =
  | "project_owner"
  | "architect"
  | "scrum_master"
  | "developer"
  | "qa";
export type ArtifactType =
  | "srs"
  | "epic_breakdown"
  | "hld"
  | "lld"
  | "sprint_plan"
  | "story_breakdown"
  | "task_breakdown"
  | "api_contract"
  | "test_plan"
  | "test_cases";
export type JobStatus =
  | "queued"
  | "running"
  | "awaiting_review"
  | "accepted"
  | "rejected"
  | "failed";
export type DocType = "srs" | "hld" | "lld" | "test_plan" | "other";
export type DocStatus = "draft" | "in_review" | "approved" | "superseded";

export const TERMINAL_JOB_STATUSES: readonly JobStatus[] = [
  "accepted",
  "rejected",
  "failed",
];

export function isTerminalStatus(status: JobStatus): boolean {
  return TERMINAL_JOB_STATUSES.includes(status);
}

/** A job the worker is actively progressing — worth streaming/polling. Settled
 * states (`awaiting_review` + the terminal set) need neither. */
export function isLiveStatus(status: JobStatus): boolean {
  return status === "queued" || status === "running";
}

export interface Job {
  readonly id: string;
  readonly project_id: string;
  readonly agent_role: AgentRole;
  readonly target_artifact: ArtifactType;
  readonly status: JobStatus;
  readonly focus_item_id: string | null;
  readonly result_document_version: string | null;
  readonly model_used: string | null;
  readonly prompt_tokens: number | null;
  readonly output_tokens: number | null;
  readonly error: string | null;
  readonly created_at: string;
  readonly started_at: string | null;
  readonly finished_at: string | null;
}

export interface GenerateArtifactRequest {
  readonly agent_role: AgentRole;
  readonly target_artifact: ArtifactType;
  readonly focus_item_id?: string | null;
  readonly instructions?: string | null;
}

export interface EnqueuedJob {
  readonly job_id: string;
  readonly status: JobStatus;
}

export interface AcceptResult {
  readonly job_id: string;
  readonly document_version_id: string | null;
}

export type ProvenanceStage = "lineage" | "semantic" | "operational";

export interface ProvenanceEntry {
  readonly id: string;
  readonly stage: ProvenanceStage;
  readonly source_chunk: string | null;
  readonly chunk_hash: string | null;
  readonly section_path: string | null;
  readonly source_item: string | null;
  readonly similarity: number | null;
}

export interface DocumentSummary {
  readonly id: string;
  readonly project_id: string;
  readonly doc_type: DocType;
  readonly title: string;
  readonly current_version_id: string | null;
  readonly created_at: string;
}

export interface DocumentVersion {
  readonly id: string;
  readonly document_id: string;
  readonly version_no: number;
  readonly content_md: string;
  readonly content_hash: string;
  readonly status: DocStatus;
  readonly change_summary: string | null;
  readonly created_by: string;
  readonly ai_job_id: string | null;
  readonly created_at: string;
  readonly approved_at: string | null;
}

/** A single SSE progress frame published by the generation worker. */
export interface ProgressFrame {
  readonly step: string;
  readonly draft_id?: string;
  readonly error?: string;
}

export function categoryBadgeVariant(
  category: WorkflowCategory,
): "secondary" | "outline" | "default" {
  switch (category) {
    case "todo":
      return "outline";
    case "in_progress":
      return "secondary";
    case "done":
      return "default";
  }
}
