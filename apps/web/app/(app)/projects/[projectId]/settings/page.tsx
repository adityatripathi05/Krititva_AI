import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { serverApi } from "@/lib/api/server";
import { categoryBadgeVariant } from "@/lib/api/types";
import type {
  HierarchyRule,
  Project,
  WorkflowState,
  WorkflowTransition,
} from "@/lib/api/types";

export default async function ProjectSettingsPage({
  params,
}: {
  readonly params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  const [project, states, transitions, hierarchy] = await Promise.all([
    serverApi<Project>(`/projects/${projectId}`),
    serverApi<WorkflowState[]>(`/projects/${projectId}/workflow/states`),
    serverApi<WorkflowTransition[]>(`/projects/${projectId}/workflow/transitions`),
    serverApi<HierarchyRule[]>(`/projects/${projectId}/hierarchy-rules`),
  ]);
  const stateLabel = new Map(states.map((s) => [s.id, s.label]));
  const gen = (project.llm_config.generation_models ?? {}) as Record<string, string>;

  return (
    <div className="mx-auto w-full max-w-4xl space-y-8 px-6 py-8">
      <Card>
        <CardHeader>
          <CardTitle>Workflow states</CardTitle>
          <CardDescription>
            Board columns seeded from the {project.methodology} template. Methodology
            is data — editing lands with the config UI in a later milestone.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {states.map((s) => (
            <Badge key={s.id} variant={categoryBadgeVariant(s.category)}>
              {s.label}
            </Badge>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Transitions</CardTitle>
          <CardDescription>
            Allowed moves. Hard gates require an approval quorum before a work item
            may cross them.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="divide-y divide-border text-sm">
            {transitions.map((t) => (
              <li key={t.id} className="flex flex-wrap items-center gap-2 py-2">
                <span className="font-medium">
                  {stateLabel.get(t.from_state) ?? t.from_state}
                </span>
                <span className="text-muted-foreground">→</span>
                <span className="font-medium">
                  {stateLabel.get(t.to_state) ?? t.to_state}
                </span>
                {t.required_role ? (
                  <Badge variant="outline">requires {t.required_role}</Badge>
                ) : null}
                {t.is_hard_gate ? <Badge variant="destructive">hard gate</Badge> : null}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Work item hierarchy</CardTitle>
          <CardDescription>Which item kinds may nest under which.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {hierarchy.map((r) => (
            <Badge key={`${r.parent_kind}/${r.child_kind}`} variant="secondary">
              {r.parent_kind} › {r.child_kind}
            </Badge>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>AI &amp; LLM configuration</CardTitle>
          <CardDescription>
            Per-project model routing. Editing arrives with the LLM config endpoint
            in a later milestone — read-only for now.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">AI enabled</span>
            <Badge variant={project.ai_enabled ? "default" : "outline"}>
              {project.ai_enabled ? "on" : "off"}
            </Badge>
          </div>
          {Object.entries(gen).map(([tier, model]) => (
            <div key={tier} className="flex items-center justify-between">
              <span className="text-muted-foreground capitalize">{tier} model</span>
              <span className="font-mono">{model}</span>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
