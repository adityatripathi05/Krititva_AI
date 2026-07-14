import { AIPanel } from "@/components/ai/ai-panel";

export default async function AIPage({
  params,
}: {
  readonly params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <AIPanel projectId={projectId} />;
}
