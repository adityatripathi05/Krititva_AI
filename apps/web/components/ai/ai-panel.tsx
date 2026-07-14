"use client";

import * as React from "react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import { GenerateForm } from "./generate-form";
import { JobDetail } from "./job-detail";
import { JobList } from "./job-list";

export function AIPanel({ projectId }: { readonly projectId: string }) {
  const [selectedId, setSelectedId] = React.useState<string | null>(null);

  return (
    <div className="grid gap-6 px-6 py-6 lg:grid-cols-[22rem_1fr]">
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Generate</CardTitle>
          </CardHeader>
          <CardContent>
            <GenerateForm projectId={projectId} onEnqueued={setSelectedId} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Jobs</CardTitle>
          </CardHeader>
          <CardContent>
            <JobList
              projectId={projectId}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="pt-6">
          {selectedId === null ? (
            <p className="text-sm text-muted-foreground">
              Select a job to review its draft, provenance, and citations — or
              generate a new draft.
            </p>
          ) : (
            <JobDetail projectId={projectId} jobId={selectedId} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
