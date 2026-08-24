"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { postCallStatusLabel, recommendationBadgeClass, statusBadgeVariant } from "@/lib/badges";
import { apiGet, apiPost, ApiError } from "@/lib/api";
import type { CallDetail, CandidateSummary, InterviewDetail } from "@/lib/types";
import { TERMINAL_CALL_STATUSES } from "@/lib/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Phone, Plus, RotateCw } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

type CandidateDraft = { callee_name: string; mobile_number: string };

function isSettled(candidate: CandidateSummary): boolean {
  if (!TERMINAL_CALL_STATUSES.has(candidate.status)) return false;
  return candidate.transcript_status !== "pending" && candidate.scorecard_status !== "pending";
}

function FunnelBadges({ counts, emptyLabel }: { counts: Record<string, number>; emptyLabel: string }) {
  const entries = Object.entries(counts);
  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">{emptyLabel}</p>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {entries.map(([key, count]) => (
        <Badge key={key} variant="secondary" className="font-normal">
          {key}: {count}
        </Badge>
      ))}
    </div>
  );
}

function AddCandidatesDialog({ interviewId }: { interviewId: string }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [drafts, setDrafts] = useState<CandidateDraft[]>([{ callee_name: "", mobile_number: "" }]);
  const [dispatchNow, setDispatchNow] = useState(true);

  const addMutation = useMutation({
    mutationFn: () => {
      const candidates = drafts.filter((d) => d.callee_name && d.mobile_number);
      const path = `/api/hiring/interviews/${interviewId}/candidates?dispatch=${dispatchNow}`;
      return apiPost<CandidateSummary[]>(path, { candidates });
    },
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ["interview", interviewId] });
      toast.success(`Added ${created.length} candidate(s)`);
      setOpen(false);
      setDrafts([{ callee_name: "", mobile_number: "" }]);
    },
    onError: (error: unknown) => {
      toast.error(error instanceof ApiError ? error.message : "Failed to add candidates");
    },
  });

  function updateDraft(index: number, field: keyof CandidateDraft, value: string) {
    setDrafts((prev) => prev.map((d, i) => (i === index ? { ...d, [field]: value } : d)));
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="h-4 w-4" />
          Add candidate(s)
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Add candidates</DialogTitle>
          <DialogDescription>They&apos;ll be dispatched immediately unless you turn that off below.</DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            addMutation.mutate();
          }}
        >
          <div className="flex flex-col gap-3">
            {drafts.map((draft, index) => (
              <div key={index} className="flex gap-2">
                <Input
                  value={draft.callee_name}
                  onChange={(e) => updateDraft(index, "callee_name", e.target.value)}
                  placeholder="Candidate name"
                  required
                />
                <Input
                  value={draft.mobile_number}
                  onChange={(e) => updateDraft(index, "mobile_number", e.target.value)}
                  placeholder="+15551234567"
                  required
                />
              </div>
            ))}
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="self-start"
            onClick={() => setDrafts((prev) => [...prev, { callee_name: "", mobile_number: "" }])}
          >
            <Plus className="h-4 w-4" />
            Add another
          </Button>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={dispatchNow}
              onChange={(e) => setDispatchNow(e.target.checked)}
              className="h-4 w-4"
            />
            Dispatch now
          </label>

          <DialogFooter>
            <Button type="submit" disabled={addMutation.isPending}>
              {addMutation.isPending ? "Adding..." : "Add candidate(s)"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function CandidateDetailDialog({ candidateId, onOpenChange }: { candidateId: string; onOpenChange: (open: boolean) => void }) {
  const queryClient = useQueryClient();
  const callQuery = useQuery({
    queryKey: ["call", candidateId],
    queryFn: () => apiGet<CallDetail>(`/api/calls/${candidateId}`),
    refetchInterval: (query) => {
      const call = query.state.data?.call;
      if (!call) return 2000;
      const settled = TERMINAL_CALL_STATUSES.has(call.status) && call.transcript_status !== "pending" && call.scorecard_status !== "pending";
      return settled ? false : 2000;
    },
    refetchIntervalInBackground: true,
  });

  const rescoreMutation = useMutation({
    mutationFn: () => apiPost(`/api/hiring/candidates/${candidateId}/rescore`, {}),
    onSuccess: () => {
      toast.success("Re-running transcript + scorecard");
      queryClient.invalidateQueries({ queryKey: ["call", candidateId] });
    },
    onError: (error: unknown) => {
      toast.error(error instanceof ApiError ? error.message : "Failed to rescore");
    },
  });

  const call = callQuery.data?.call;
  const events = callQuery.data?.events ?? [];

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        {callQuery.isLoading && <Skeleton className="h-64 w-full" />}
        {call && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                {call.callee_name}
                <Badge variant={statusBadgeVariant(call.status)}>{call.status}</Badge>
              </DialogTitle>
              <DialogDescription>{call.mobile_number}</DialogDescription>
            </DialogHeader>

            <Tabs defaultValue="scorecard">
              <TabsList>
                <TabsTrigger value="result">Result</TabsTrigger>
                <TabsTrigger value="scorecard">Scorecard</TabsTrigger>
                <TabsTrigger value="transcript">Transcript</TabsTrigger>
                <TabsTrigger value="timeline">Timeline</TabsTrigger>
                <TabsTrigger value="recording">Recording</TabsTrigger>
              </TabsList>

              <TabsContent value="result" className="max-h-96 overflow-y-auto">
                {call.result ? (
                  <dl className="flex flex-col gap-2 text-sm">
                    {Object.entries(call.result).map(([key, value]) => (
                      <div key={key} className="flex justify-between gap-4 border-b pb-1">
                        <dt className="text-muted-foreground">{key}</dt>
                        <dd className="text-right">{String(value)}</dd>
                      </div>
                    ))}
                  </dl>
                ) : (
                  <p className="text-sm text-muted-foreground">No structured result yet.</p>
                )}
              </TabsContent>

              <TabsContent value="scorecard" className="flex max-h-96 flex-col gap-4 overflow-y-auto">
                {call.scorecard_status === "pending" && <Skeleton className="h-40 w-full" />}
                {call.scorecard_status === "failed" && (
                  <p className="text-sm text-destructive">Scorecard generation failed: {call.scorecard_error}</p>
                )}
                {call.scorecard_status === "skipped" && (
                  <p className="text-sm text-muted-foreground">Scorecard generation was skipped.</p>
                )}
                {call.scorecard && (
                  <>
                    <div className="flex items-center gap-3">
                      <Badge className={recommendationBadgeClass(call.scorecard.recommendation)} variant="secondary">
                        {call.scorecard.recommendation}
                      </Badge>
                      <span className="text-lg font-semibold">{call.scorecard.overall_score}/100</span>
                    </div>
                    <p className="text-sm">{call.scorecard.summary}</p>

                    <div className="flex flex-col gap-2">
                      {call.scorecard.competencies.map((c) => (
                        <div key={c.name} className="flex flex-col gap-1">
                          <div className="flex justify-between text-sm">
                            <span>{c.name}</span>
                            <span className="text-muted-foreground">{c.score}/100</span>
                          </div>
                          <Progress value={c.score} />
                          <p className="text-xs text-muted-foreground">{c.notes}</p>
                        </div>
                      ))}
                    </div>

                    {call.scorecard.strengths.length > 0 && (
                      <div>
                        <p className="mb-1 text-sm font-medium">Strengths</p>
                        <ul className="list-inside list-disc text-sm text-muted-foreground">
                          {call.scorecard.strengths.map((s, i) => (
                            <li key={i}>{s}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {call.scorecard.concerns.length > 0 && (
                      <div>
                        <p className="mb-1 text-sm font-medium">Concerns</p>
                        <ul className="list-inside list-disc text-sm text-muted-foreground">
                          {call.scorecard.concerns.map((s, i) => (
                            <li key={i}>{s}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {call.scorecard.red_flags.length > 0 && (
                      <div>
                        <p className="mb-1 text-sm font-medium text-destructive">Red flags</p>
                        <ul className="list-inside list-disc text-sm text-destructive">
                          {call.scorecard.red_flags.map((s, i) => (
                            <li key={i}>{s}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {call.scorecard.suggested_followups.length > 0 && (
                      <div>
                        <p className="mb-1 text-sm font-medium">Suggested follow-ups</p>
                        <ul className="list-inside list-disc text-sm text-muted-foreground">
                          {call.scorecard.suggested_followups.map((s, i) => (
                            <li key={i}>{s}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </>
                )}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="self-start"
                  onClick={() => rescoreMutation.mutate()}
                  disabled={rescoreMutation.isPending}
                >
                  <RotateCw className="h-4 w-4" />
                  Rescore
                </Button>
              </TabsContent>

              <TabsContent value="transcript" className="max-h-96 overflow-y-auto">
                {call.transcript_status === "pending" && <Skeleton className="h-40 w-full" />}
                {call.transcript_status === "failed" && (
                  <p className="text-sm text-destructive">Transcription failed: {call.transcript_error}</p>
                )}
                {call.transcript_status === "skipped" && (
                  <p className="text-sm text-muted-foreground">Transcription was skipped or not available.</p>
                )}
                {call.transcript && <pre className="whitespace-pre-wrap text-sm">{call.transcript}</pre>}
              </TabsContent>

              <TabsContent value="timeline" className="max-h-96 overflow-y-auto">
                <ol className="flex flex-col gap-1.5">
                  {events.map((event) => (
                    <li key={event.id} className="flex items-center gap-2 text-sm">
                      <span className="text-muted-foreground">{new Date(event.received_at).toLocaleTimeString()}</span>
                      <Badge variant="outline">{event.source}</Badge>
                      <span>{event.event_type}</span>
                    </li>
                  ))}
                  {events.length === 0 && <li className="text-sm text-muted-foreground">No events yet.</li>}
                </ol>
              </TabsContent>

              <TabsContent value="recording">
                {call.recording_url ? (
                  <audio controls className="w-full" src={call.recording_url}>
                    Your browser does not support audio playback.
                  </audio>
                ) : (
                  <p className="text-sm text-muted-foreground">No recording available yet.</p>
                )}
              </TabsContent>
            </Tabs>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default function InterviewDetailPage() {
  const params = useParams<{ id: string }>();
  const interviewId = params.id;
  const queryClient = useQueryClient();
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);

  const interviewQuery = useQuery({
    queryKey: ["interview", interviewId],
    queryFn: () => apiGet<InterviewDetail>(`/api/hiring/interviews/${interviewId}`),
    refetchInterval: (query) => {
      const candidates = query.state.data?.candidates ?? [];
      return candidates.some((c) => !isSettled(c)) ? 2500 : false;
    },
    refetchIntervalInBackground: true,
  });

  const dispatchMutation = useMutation({
    mutationFn: (candidateId: string) => apiPost(`/api/hiring/candidates/${candidateId}/dispatch`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["interview", interviewId] });
      toast.success("Dispatched");
    },
    onError: (error: unknown) => {
      toast.error(error instanceof ApiError ? error.message : "Dispatch failed");
    },
  });

  const interview = interviewQuery.data;

  return (
    <div className="flex flex-col gap-6 p-8">
      <div>
        <Link href="/hiring-assistant" className="mb-2 flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" />
          Interviews
        </Link>
        {interviewQuery.isLoading && <Skeleton className="h-8 w-64" />}
        {interview && (
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">{interview.title}</h1>
              {interview.description && <p className="max-w-2xl text-muted-foreground">{interview.description}</p>}
            </div>
            <AddCandidatesDialog interviewId={interviewId} />
          </div>
        )}
      </div>

      {interview && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Summary</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 sm:flex-row sm:gap-8">
            <div>
              <p className="mb-1 text-xs font-medium uppercase text-muted-foreground">By status</p>
              <FunnelBadges counts={interview.funnel.by_status} emptyLabel="No candidates yet" />
            </div>
            <div>
              <p className="mb-1 text-xs font-medium uppercase text-muted-foreground">By recommendation</p>
              <FunnelBadges counts={interview.funnel.by_recommendation} emptyLabel="No scorecards yet" />
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="pt-6">
          {interviewQuery.isLoading && <Skeleton className="h-48 w-full" />}
          {interview && interview.candidates.length === 0 && (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No candidates yet. Add some to start dispatching interviews.
            </p>
          )}
          {interview && interview.candidates.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Candidate</TableHead>
                  <TableHead>Phone</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Transcript</TableHead>
                  <TableHead>Recommendation</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {interview.candidates.map((candidate) => (
                  <TableRow
                    key={candidate.id}
                    className="cursor-pointer"
                    onClick={() => setSelectedCandidateId(candidate.id)}
                  >
                    <TableCell className="font-medium">{candidate.callee_name}</TableCell>
                    <TableCell>{candidate.mobile_number}</TableCell>
                    <TableCell>
                      <Badge variant={statusBadgeVariant(candidate.status)}>{candidate.status}</Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {postCallStatusLabel(candidate.transcript_status)}
                    </TableCell>
                    <TableCell>
                      {candidate.recommendation ? (
                        <Badge className={recommendationBadgeClass(candidate.recommendation)} variant="secondary">
                          {candidate.recommendation}
                        </Badge>
                      ) : (
                        <span className="text-sm text-muted-foreground">
                          {postCallStatusLabel(candidate.scorecard_status)}
                        </span>
                      )}
                    </TableCell>
                    <TableCell>{candidate.overall_score ?? "—"}</TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      {(!candidate.provider_call_id || candidate.status === "FAILED") && (
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => dispatchMutation.mutate(candidate.id)}
                          disabled={dispatchMutation.isPending}
                        >
                          <Phone className="h-3.5 w-3.5" />
                          {candidate.provider_call_id ? "Retry" : "Dispatch"}
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {selectedCandidateId && (
        <CandidateDetailDialog
          candidateId={selectedCandidateId}
          onOpenChange={(open) => {
            if (!open) setSelectedCandidateId(null);
          }}
        />
      )}
    </div>
  );
}
