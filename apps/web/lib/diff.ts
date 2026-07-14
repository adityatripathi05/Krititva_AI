export type DiffType = "equal" | "added" | "removed";

export interface DiffRow {
  readonly left: string | null;
  readonly right: string | null;
  readonly leftNo: number | null;
  readonly rightNo: number | null;
  readonly type: DiffType;
}

/**
 * Line-level diff via longest-common-subsequence, aligned for a side-by-side
 * view: removed lines occupy the left column, added lines the right, unchanged
 * lines both. Self-contained (no dependency) — inputs are document-sized, so the
 * O(n·m) table is fine.
 */
export function lineDiff(before: string, after: string): DiffRow[] {
  const a = before.length > 0 ? before.split("\n") : [];
  const b = after.length > 0 ? after.split("\n") : [];
  const n = a.length;
  const m = b.length;

  const dp: number[][] = Array.from({ length: n + 1 }, () =>
    new Array<number>(m + 1).fill(0),
  );
  for (let i = n - 1; i >= 0; i--) {
    const dpi = dp[i]!;
    const dpNext = dp[i + 1]!;
    const ai = a[i]!;
    for (let j = m - 1; j >= 0; j--) {
      dpi[j] = ai === b[j]! ? dpNext[j + 1]! + 1 : Math.max(dpNext[j]!, dpi[j + 1]!);
    }
  }

  const rows: DiffRow[] = [];
  let i = 0;
  let j = 0;
  let leftNo = 1;
  let rightNo = 1;
  while (i < n && j < m) {
    const ai = a[i]!;
    const bj = b[j]!;
    if (ai === bj) {
      rows.push({ left: ai, right: bj, leftNo: leftNo++, rightNo: rightNo++, type: "equal" });
      i++;
      j++;
    } else if (dp[i + 1]![j]! >= dp[i]![j + 1]!) {
      rows.push({ left: ai, right: null, leftNo: leftNo++, rightNo: null, type: "removed" });
      i++;
    } else {
      rows.push({ left: null, right: bj, leftNo: null, rightNo: rightNo++, type: "added" });
      j++;
    }
  }
  while (i < n) {
    rows.push({ left: a[i]!, right: null, leftNo: leftNo++, rightNo: null, type: "removed" });
    i++;
  }
  while (j < m) {
    rows.push({ left: null, right: b[j]!, leftNo: null, rightNo: rightNo++, type: "added" });
    j++;
  }
  return rows;
}

export interface DiffStats {
  readonly added: number;
  readonly removed: number;
}

export function diffStats(rows: readonly DiffRow[]): DiffStats {
  let added = 0;
  let removed = 0;
  for (const row of rows) {
    if (row.type === "added") added++;
    else if (row.type === "removed") removed++;
  }
  return { added, removed };
}
