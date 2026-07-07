import type { Metadata } from "next";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { categoryVariant, loadProjectSettings } from "@/lib/methodology";

export const metadata: Metadata = {
  title: "Project settings",
};

export default async function ProjectSettingsPage({
  params,
}: {
  readonly params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  const settings = await loadProjectSettings(projectId);
  const stateLabel = new Map(settings.states.map((s) => [s.key, s.label]));

  return (
    <main className="container mx-auto max-w-4xl space-y-8 px-6 py-10">
      <header className="space-y-1">
        <p className="text-sm uppercase tracking-widest text-muted-foreground">
          Project settings
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">{settings.name}</h1>
        <p className="text-sm text-muted-foreground">
          <span className="font-mono">{settings.key}</span> ·{" "}
          <span className="capitalize">{settings.methodology}</span> methodology
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>Workflow states</CardTitle>
          <CardDescription>
            The board columns work items move through. Methodology is data — these
            were seeded from the {settings.methodology} template on project creation.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {settings.states.map((state) => (
            <Badge key={state.key} variant={categoryVariant(state.category)}>
              {state.label}
            </Badge>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Transitions</CardTitle>
          <CardDescription>
            Allowed moves between states. Hard gates require an approval quorum
            before a work item may cross them.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="divide-y divide-border text-sm">
            {settings.transitions.map((t) => (
              <li
                key={`${t.fromKey}->${t.toKey}`}
                className="flex flex-wrap items-center gap-2 py-2"
              >
                <span className="font-medium">{stateLabel.get(t.fromKey) ?? t.fromKey}</span>
                <span className="text-muted-foreground">→</span>
                <span className="font-medium">{stateLabel.get(t.toKey) ?? t.toKey}</span>
                {t.requiredRole ? (
                  <Badge variant="outline">requires {t.requiredRole}</Badge>
                ) : null}
                {t.isHardGate ? <Badge variant="destructive">hard gate</Badge> : null}
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
          {settings.hierarchy.map((rule) => (
            <Badge key={`${rule.parentKind}/${rule.childKind}`} variant="secondary">
              {rule.parentKind} › {rule.childKind}
            </Badge>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>AI &amp; LLM configuration</CardTitle>
          <CardDescription>
            Per-project model routing. Editing lands with the LLM config endpoint
            in a later milestone — read-only placeholder for now.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">AI enabled</span>
            <Badge variant={settings.aiEnabled ? "default" : "outline"}>
              {settings.aiEnabled ? "on" : "off"}
            </Badge>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Retrieval model</span>
            <span className="font-mono">{settings.llmConfig.retrievalModel}</span>
          </div>
          {(["frontier", "mid", "fast"] as const).map((tier) => (
            <div key={tier} className="flex items-center justify-between">
              <span className="text-muted-foreground capitalize">{tier} model</span>
              <span className="font-mono">{settings.llmConfig.generationModels[tier]}</span>
            </div>
          ))}
        </CardContent>
      </Card>
    </main>
  );
}
