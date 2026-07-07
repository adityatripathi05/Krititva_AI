import { BacklogList } from "@/components/backlog/backlog-list";

export default async function BacklogPage({
  params,
}: {
  readonly params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <BacklogList projectId={projectId} />;
}
