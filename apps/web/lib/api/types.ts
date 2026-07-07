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
