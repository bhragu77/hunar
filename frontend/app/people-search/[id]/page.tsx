"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { apiGet, apiPatch, apiPost, ApiError } from "@/lib/api";
import { outreachBucketBadgeClass, outreachBucketBadgeVariant, statusBadgeVariant } from "@/lib/badges";
import type { Agent, CallDetail, DispatchResult, OutreachCampaignDetail, SearchCriteria, SourcedCandidate } from "@/lib/types";
import { TERMINAL_CALL_STATUSES } from "@/lib/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Phone, RotateCw, Search } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

function listToText(values: string[]): string {
  return values.join(", ");
}

function textToList(value: string): string[] {
  return value
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
}

function isCandidateSettled(candidate: SourcedCandidate): boolean {
  if (!candidate.call_id) return true;
  if (!candidate.call_status) return false;
  return TERMINAL_CALL_STATUSES.has(candidate.call_status);
}

function FunnelStrip({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts);
  return (
    <div className="flex flex-wrap gap-2">
      {entries.map(([bucket, count]) => (
        <Badge
          key={bucket}
          variant={outreachBucketBadgeVariant(bucket)}
          className={`px-3 py-1 text-sm font-normal ${outreachBucketBadgeClass(bucket)}`}
        >
          {bucket}: {count}
        </Badge>
      ))}
    </div>
  );
}

// --- Sourcing tab ---

function CriteriaEditor({ campaignId, criteria }: { campaignId: string; criteria: SearchCriteria }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState(criteria);

  const saveMutation = useMutation({
    mutationFn: () => apiPatch(`/api/outreach/campaigns/${campaignId}/criteria`, { criteria: draft }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["outreach-campaign", campaignId] });
      toast.success("Criteria saved");
    },
    onError: (error: unknown) => {
      toast.error(error instanceof ApiError ? error.message : "Failed to save criteria");
    },
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Search criteria</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-2">
            <Label>Titles</Label>
            <Textarea
              rows={2}
              value={listToText(draft.titles)}
              onChange={(e) => setDraft((d) => ({ ...d, titles: textToList(e.target.value) }))}
              placeholder="Backend Engineer, Software Engineer"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label>Seniorities</Label>
            <Textarea
              rows={2}
              value={listToText(draft.seniorities)}
              onChange={(e) => setDraft((d) => ({ ...d, seniorities: textToList(e.target.value) }))}
              placeholder="senior, lead"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label>Skills</Label>
            <Textarea
              rows={2}
              value={listToText(draft.skills)}
              onChange={(e) => setDraft((d) => ({ ...d, skills: textToList(e.target.value) }))}
              placeholder="python, fastapi, sql"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label>Locations</Label>
            <Textarea
              rows={2}
              value={listToText(draft.locations)}
              onChange={(e) => setDraft((d) => ({ ...d, locations: textToList(e.target.value) }))}
              placeholder="Bengaluru, Remote"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label>Industries</Label>
            <Textarea
              rows={2}
              value={listToText(draft.industries)}
              onChange={(e) => setDraft((d) => ({ ...d, industries: textToList(e.target.value) }))}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label>Keywords</Label>
            <Textarea
              rows={2}
              value={listToText(draft.keywords)}
              onChange={(e) => setDraft((d) => ({ ...d, keywords: textToList(e.target.value) }))}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label>Min years</Label>
            <Input
              type="number"
              value={draft.min_years ?? ""}
              onChange={(e) => setDraft((d) => ({ ...d, min_years: e.target.value ? Number(e.target.value) : null }))}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label>Max years</Label>
            <Input
              type="number"
              value={draft.max_years ?? ""}
              onChange={(e) => setDraft((d) => ({ ...d, max_years: e.target.value ? Number(e.target.value) : null }))}
            />
          </div>
        </div>
        <Button type="button" size="sm" className="self-start" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
          {saveMutation.isPending ? "Saving..." : "Save criteria"}
        </Button>
      </CardContent>
    </Card>
  );
}

function PhoneCell({ candidate }: { candidate: SourcedCandidate }) {
  const queryClient = useQueryClient();
  const params = useParams<{ id: string }>();
  const [value, setValue] = useState(candidate.mobile_number ?? "");

  const saveMutation = useMutation({
    mutationFn: (mobile_number: string) => apiPatch(`/api/outreach/candidates/${candidate.id}`, { mobile_number }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["outreach-campaign", params.id] });
      toast.success("Phone number saved");
    },
    onError: (error: unknown) => {
      toast.error(error instanceof ApiError ? error.message : "Failed to save phone number");
    },
  });

  if (candidate.mobile_number) {
    return <span className="text-sm">{candidate.mobile_number}</span>;
  }

  return (
    <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
      <Input
        className="h-8 w-36 text-xs"
        placeholder="+91..."
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <Button
        type="button"
        size="sm"
        variant="outline"
        className="h-8 px-2"
        disabled={!value || saveMutation.isPending}
        onClick={() => saveMutation.mutate(value)}
      >
        Save
      </Button>
    </div>
  );
}

function SourcingTab({ campaign }: { campaign: OutreachCampaignDetail }) {
  const queryClient = useQueryClient();

  const searchMutation = useMutation({
    mutationFn: () => apiPost<SourcedCandidate[]>(`/api/outreach/campaigns/${campaign.id}/search`),
    onSuccess: (candidates) => {
      queryClient.invalidateQueries({ queryKey: ["outreach-campaign", campaign.id] });
      toast.success(`Sourced ${candidates.length} candidate(s) total`);
    },
    onError: (error: unknown) => {
      toast.error(error instanceof ApiError ? error.message : "Search failed");
    },
  });

  const selectMutation = useMutation({
    mutationFn: ({ candidateId, selected }: { candidateId: string; selected: boolean }) =>
      apiPost(`/api/outreach/candidates/select`, { candidate_ids: [candidateId], selected }),
    // Optimistic update: the checkbox is a controlled input bound straight to server state,
    // so without this it visually snaps back to unchecked for the length of the round trip.
    onMutate: async ({ candidateId, selected }) => {
      const queryKey = ["outreach-campaign", campaign.id];
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<OutreachCampaignDetail>(queryKey);
      queryClient.setQueryData<OutreachCampaignDetail>(queryKey, (current) =>
        current
          ? {
              ...current,
              candidates: current.candidates.map((c) => (c.id === candidateId ? { ...c, selected } : c)),
            }
          : current,
      );
      return { previous };
    },
    onError: (error: unknown, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(["outreach-campaign", campaign.id], context.previous);
      }
      toast.error(error instanceof ApiError ? error.message : "Failed to update selection");
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["outreach-campaign", campaign.id] });
    },
  });

  const dispatchMutation = useMutation({
    mutationFn: () => apiPost<DispatchResult>(`/api/outreach/campaigns/${campaign.id}/dispatch`),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["outreach-campaign", campaign.id] });
      toast.success(`Dispatched ${result.dispatched.length} call(s)`);
      if (result.skipped_no_phone.length > 0) {
        toast.warning(`${result.skipped_no_phone.length} candidate(s) skipped - no phone number`);
      }
    },
    onError: (error: unknown) => {
      toast.error(error instanceof ApiError ? error.message : "Dispatch failed");
    },
  });

  const selectedCount = campaign.candidates.filter((c) => c.selected && !c.call_id).length;

  return (
    <div className="flex flex-col gap-4">
      <CriteriaEditor key={campaign.id} campaignId={campaign.id} criteria={campaign.criteria} />

      <div className="flex items-center justify-between">
        <Button type="button" onClick={() => searchMutation.mutate()} disabled={searchMutation.isPending}>
          <Search className="h-4 w-4" />
          {searchMutation.isPending ? "Searching..." : "Search candidates"}
        </Button>
        <Button
          type="button"
          variant="secondary"
          onClick={() => dispatchMutation.mutate()}
          disabled={selectedCount === 0 || dispatchMutation.isPending || !campaign.agent_id}
        >
          <Phone className="h-4 w-4" />
          {dispatchMutation.isPending ? "Dispatching..." : `Dispatch selected (${selectedCount})`}
        </Button>
      </div>

      <Card>
        <CardContent className="pt-6">
          {campaign.candidates.length === 0 && (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No candidates sourced yet. Run a search to find profiles matching the criteria above.
            </p>
          )}
          {campaign.candidates.length > 0 && (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-10" />
                    <TableHead>Name</TableHead>
                    <TableHead>Title</TableHead>
                    <TableHead>Company</TableHead>
                    <TableHead>Location</TableHead>
                    <TableHead>Phone</TableHead>
                    <TableHead>Match</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {campaign.candidates.map((candidate) => (
                    <TableRow key={candidate.id}>
                      <TableCell>
                        <input
                          type="checkbox"
                          className="h-4 w-4"
                          checked={candidate.selected}
                          disabled={!!candidate.call_id || selectMutation.isPending}
                          onChange={(e) => selectMutation.mutate({ candidateId: candidate.id, selected: e.target.checked })}
                        />
                      </TableCell>
                      <TableCell className="font-medium">{candidate.full_name}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">{candidate.title ?? "—"}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">{candidate.company ?? "—"}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">{candidate.location ?? "—"}</TableCell>
                      <TableCell>
                        <PhoneCell candidate={candidate} />
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {candidate.match_score != null ? `${Math.round(candidate.match_score * 100)}%` : "—"}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={outreachBucketBadgeVariant(candidate.bucket)}
                          className={`font-normal ${outreachBucketBadgeClass(candidate.bucket)}`}
                        >
                          {candidate.bucket}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// --- Reachout funnel tab ---

function CandidateCallDialog({ candidate, onOpenChange }: { candidate: SourcedCandidate; onOpenChange: (open: boolean) => void }) {
  const callQuery = useQuery({
    queryKey: ["call", candidate.call_id],
    queryFn: () => apiGet<CallDetail>(`/api/calls/${candidate.call_id}`),
    enabled: !!candidate.call_id,
    refetchInterval: (query) => {
      const call = query.state.data?.call;
      if (!call) return 2000;
      const settled = TERMINAL_CALL_STATUSES.has(call.status) && call.outreach_summary !== null;
      return settled ? false : 2000;
    },
    refetchIntervalInBackground: true,
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
                {candidate.full_name}
                <Badge variant={statusBadgeVariant(call.status)}>{call.status}</Badge>
              </DialogTitle>
              <DialogDescription>{call.mobile_number}</DialogDescription>
            </DialogHeader>

            <Tabs defaultValue="summary">
              <TabsList>
                <TabsTrigger value="summary">Summary</TabsTrigger>
                <TabsTrigger value="result">Result</TabsTrigger>
                <TabsTrigger value="transcript">Transcript</TabsTrigger>
                <TabsTrigger value="timeline">Timeline</TabsTrigger>
                <TabsTrigger value="recording">Recording</TabsTrigger>
              </TabsList>

              <TabsContent value="summary" className="max-h-96 overflow-y-auto">
                {call.outreach_summary ? (
                  <p className="text-sm">{call.outreach_summary}</p>
                ) : (
                  <Skeleton className="h-16 w-full" />
                )}
              </TabsContent>

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

              <TabsContent value="transcript" className="max-h-96 overflow-y-auto">
                {call.transcript_status === "pending" && <Skeleton className="h-40 w-full" />}
                {call.transcript_status === "failed" && (
                  <p className="text-sm text-destructive">Transcription failed: {call.transcript_error}</p>
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

function FunnelTab({ campaign }: { campaign: OutreachCampaignDetail }) {
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  const contacted = campaign.candidates.filter((c) => c.call_id);
  const selectedCandidate = contacted.find((c) => c.id === selectedCandidateId) ?? null;

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Funnel</CardTitle>
        </CardHeader>
        <CardContent>
          <FunnelStrip counts={campaign.funnel.counts} />
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          {contacted.length === 0 && (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No candidates contacted yet. Select and dispatch from the Sourcing tab.
            </p>
          )}
          {contacted.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Candidate</TableHead>
                  <TableHead>Phone</TableHead>
                  <TableHead>Call status</TableHead>
                  <TableHead>Bucket</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {contacted.map((candidate) => (
                  <TableRow key={candidate.id} className="cursor-pointer" onClick={() => setSelectedCandidateId(candidate.id)}>
                    <TableCell className="font-medium">{candidate.full_name}</TableCell>
                    <TableCell>{candidate.mobile_number}</TableCell>
                    <TableCell>
                      <Badge variant={statusBadgeVariant(candidate.call_status ?? "")}>{candidate.call_status}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={outreachBucketBadgeVariant(candidate.bucket)}
                        className={`font-normal ${outreachBucketBadgeClass(candidate.bucket)}`}
                      >
                        {candidate.bucket}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {selectedCandidate && (
        <CandidateCallDialog
          candidate={selectedCandidate}
          onOpenChange={(open) => {
            if (!open) setSelectedCandidateId(null);
          }}
        />
      )}
    </div>
  );
}

// --- Agent tab ---

function AgentTab({ campaign }: { campaign: OutreachCampaignDetail }) {
  const queryClient = useQueryClient();
  const [pickedAgentId, setPickedAgentId] = useState("");

  const agentsQuery = useQuery({
    queryKey: ["agents"],
    queryFn: () => apiGet<Agent[]>("/api/agents"),
    enabled: !campaign.agent_id,
  });

  const setAgentMutation = useMutation({
    mutationFn: () => apiPost(`/api/outreach/campaigns/${campaign.id}/agent`, { agent_id: pickedAgentId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["outreach-campaign", campaign.id] });
      toast.success("Agent assigned");
    },
    onError: (error: unknown) => {
      toast.error(error instanceof ApiError ? error.message : "Failed to assign agent");
    },
  });

  const regenerateMutation = useMutation({
    mutationFn: () => apiPost(`/api/outreach/campaigns/${campaign.id}/agent?regenerate=true`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["outreach-campaign", campaign.id] });
      toast.success("Agent regenerated");
    },
    onError: (error: unknown) => {
      toast.error(error instanceof ApiError ? error.message : "Failed to regenerate agent");
    },
  });

  const spec = campaign.agent_spec;

  return (
    <div className="flex flex-col gap-4">
      {!campaign.agent_id && (
        <Card className="border-destructive/50">
          <CardHeader>
            <CardTitle className="text-base text-destructive">Agent not created</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <p className="text-sm text-muted-foreground">
              {campaign.agent_create_error || "Auto-creation didn't run or failed."} Pick an existing agent or regenerate.
            </p>
            <div className="flex items-center gap-2">
              <Select value={pickedAgentId} onValueChange={setPickedAgentId}>
                <SelectTrigger className="w-64">
                  <SelectValue placeholder="Select an existing agent" />
                </SelectTrigger>
                <SelectContent>
                  {agentsQuery.data?.map((agent) => (
                    <SelectItem key={agent.id} value={agent.id}>
                      {agent.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button type="button" size="sm" disabled={!pickedAgentId || setAgentMutation.isPending} onClick={() => setAgentMutation.mutate()}>
                Set agent
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">{spec.name}</CardTitle>
          <Button type="button" variant="outline" size="sm" onClick={() => regenerateMutation.mutate()} disabled={regenerateMutation.isPending}>
            <RotateCw className="h-3.5 w-3.5" />
            {regenerateMutation.isPending ? "Regenerating..." : "Regenerate"}
          </Button>
        </CardHeader>
        <CardContent className="flex flex-col gap-4 text-sm">
          <div className="flex flex-wrap gap-2">
            <Badge variant="secondary">{spec.language}</Badge>
            <Badge variant="secondary">{spec.voice_persona}</Badge>
            <Badge variant="secondary">{spec.persona_name}</Badge>
            {campaign.agent_id && <Badge variant="outline">{campaign.agent_id}</Badge>}
          </div>
          <div>
            <p className="mb-1 font-medium">Objective</p>
            <p className="text-muted-foreground">{spec.objective}</p>
          </div>
          <div>
            <p className="mb-1 font-medium">Introduction</p>
            <p className="text-muted-foreground">{spec.introduction}</p>
          </div>
          <div>
            <p className="mb-1 font-medium">Agent prompt</p>
            <p className="whitespace-pre-wrap text-muted-foreground">{spec.agent_prompt}</p>
          </div>
          <div>
            <p className="mb-1 font-medium">Result prompt</p>
            <p className="text-muted-foreground">{spec.result_prompt}</p>
          </div>
          <div>
            <p className="mb-1 font-medium">Result schema</p>
            <dl className="flex flex-col gap-1">
              {Object.entries(spec.result_schema).map(([key, kind]) => (
                <div key={key} className="flex justify-between gap-4 border-b pb-1">
                  <dt className="text-muted-foreground">{key}</dt>
                  <dd>{String(kind)}</dd>
                </div>
              ))}
            </dl>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default function OutreachCampaignDetailPage() {
  const params = useParams<{ id: string }>();
  const campaignId = params.id;

  const campaignQuery = useQuery({
    queryKey: ["outreach-campaign", campaignId],
    queryFn: () => apiGet<OutreachCampaignDetail>(`/api/outreach/campaigns/${campaignId}`),
    refetchInterval: (query) => {
      const candidates = query.state.data?.candidates ?? [];
      return candidates.some((c) => !isCandidateSettled(c)) ? 2500 : false;
    },
    refetchIntervalInBackground: true,
  });

  const campaign = campaignQuery.data;

  return (
    <div className="flex flex-col gap-6 p-8">
      <div>
        <Link href="/people-search" className="mb-2 flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" />
          People Search
        </Link>
        {campaignQuery.isLoading && <Skeleton className="h-8 w-64" />}
        {campaign && (
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{campaign.title}</h1>
            <p className="max-w-3xl text-sm text-muted-foreground">{campaign.job_description}</p>
          </div>
        )}
      </div>

      {campaign && (
        <Tabs defaultValue="sourcing">
          <TabsList>
            <TabsTrigger value="sourcing">Sourcing</TabsTrigger>
            <TabsTrigger value="funnel">Reachout funnel</TabsTrigger>
            <TabsTrigger value="agent">Agent</TabsTrigger>
          </TabsList>
          <TabsContent value="sourcing">
            <SourcingTab campaign={campaign} />
          </TabsContent>
          <TabsContent value="funnel">
            <FunnelTab campaign={campaign} />
          </TabsContent>
          <TabsContent value="agent">
            <AgentTab campaign={campaign} />
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}
