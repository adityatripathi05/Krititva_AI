import { KanbanBoard } from "@/components/board/kanban-board";

export default async function BoardPage({
  params,
}: {
  readonly params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <KanbanBoard projectId={projectId} />;
}
