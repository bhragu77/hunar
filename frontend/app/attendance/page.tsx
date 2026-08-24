"use client";

import { Markdown } from "@/components/markdown";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { apiGet, apiPost, ApiError } from "@/lib/api";
import { attendanceRateHeatColor, attendanceStatusBadgeClass, attendanceStatusBadgeVariant } from "@/lib/badges";
import type {
  AttendanceStatus,
  CallDetail,
  DispatchRunResponse,
  LocationAttendanceSummary,
  LocationDetail,
  LocationOut,
  RunDetail,
  RunSummary,
  SeedDemoResponse,
  SimulateMissedCallsResponse,
  WorkerAttendanceOut,
} from "@/lib/types";
import { TERMINAL_CALL_STATUSES } from "@/lib/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck, MapPin, PhoneCall, RadioTower, Sprout } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

const STATUS_ORDER: AttendanceStatus[] = ["present", "absent", "unreachable", "pending"];

function CountsStrip({ counts }: { counts: RunDetail["counts"] }) {
  return (
    <div className="flex flex-wrap gap-2">
      {STATUS_ORDER.map((status) => (
        <Badge
          key={status}
          variant={attendanceStatusBadgeVariant(status)}
          className={`px-3 py-1 text-sm font-normal capitalize ${attendanceStatusBadgeClass(status)}`}
        >
          {status}: {counts[status]}
        </Badge>
      ))}
    </div>
  );
}

// --- Location drill-down ---

function SupervisorCallPanel({ callId }: { callId: string }) {
  const callQuery = useQuery({
    queryKey: ["call", callId],
    queryFn: () => apiGet<CallDetail>(`/api/calls/${callId}`),
    refetchInterval: (query) => {
      const call = query.state.data?.call;
      return call && TERMINAL_CALL_STATUSES.has(call.status) ? false : 2000;
    },
  });
  const call = callQuery.data?.call;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <PhoneCall className="h-4 w-4 text-muted-foreground" />
          Supervisor roll-call
          {call && <Badge variant="secondary">{call.status}</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        {callQuery.isLoading && <Skeleton className="h-16 w-full" />}
        {call && (
          <>
            <p className="text-muted-foreground">
              {call.callee_name} - {call.mobile_number}
            </p>

            <Tabs defaultValue="result">
              <TabsList>
                <TabsTrigger value="result">Result</TabsTrigger>
                <TabsTrigger value="transcript">Transcript</TabsTrigger>
                <TabsTrigger value="recording">Recording</TabsTrigger>
              </TabsList>

              <TabsContent value="result" className="max-h-64 overflow-y-auto">
                {call.result ? (
                  <dl className="flex flex-col gap-1">
                    {Object.entries(call.result).map(([key, value]) => (
                      <div key={key} className="flex justify-between gap-4 border-b pb-1">
                        <dt className="text-muted-foreground">{key}</dt>
                        <dd className="max-w-[60%] text-right">{String(value)}</dd>
                      </div>
                    ))}
                  </dl>
                ) : (
                  <p className="text-muted-foreground">No structured result yet.</p>
                )}
              </TabsContent>

              <TabsContent value="transcript" className="max-h-64 overflow-y-auto">
                {call.transcript_status === "pending" && <Skeleton className="h-16 w-full" />}
                {call.transcript_status === "failed" && (
                  <p className="text-destructive">Transcription failed: {call.transcript_error}</p>
                )}
                {call.transcript ? (
                  <p className="whitespace-pre-wrap text-muted-foreground">{call.transcript}</p>
                ) : (
                  call.transcript_status !== "pending" && (
                    <p className="text-muted-foreground">No transcript available.</p>
                  )
                )}
              </TabsContent>

              <TabsContent value="recording">
                {call.recording_url ? (
                  <audio controls className="w-full" src={call.recording_url}>
                    Your browser does not support audio playback.
                  </audio>
                ) : (
                  <p className="text-muted-foreground">No recording available yet.</p>
                )}
              </TabsContent>
            </Tabs>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function WorkerRow({ runId, locationId, worker }: { runId: string; locationId: string; worker: WorkerAttendanceOut }) {
  const queryClient = useQueryClient();

  const markMutation = useMutation({
    mutationFn: (status: AttendanceStatus) =>
      apiPost(`/api/attendance/records/${worker.record_id}/mark`, { status, reason: "Manual override" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["attendance-location", runId, locationId] });
      queryClient.invalidateQueries({ queryKey: ["attendance-run", runId] });
      toast.success(`${worker.full_name} marked`);
    },
    onError: (error: unknown) => {
      toast.error(error instanceof ApiError ? error.message : "Failed to update status");
    },
  });

  return (
    <TableRow>
      <TableCell className="font-medium">{worker.full_name}</TableCell>
      <TableCell className="text-sm text-muted-foreground">{worker.employee_id}</TableCell>
      <TableCell className="text-sm text-muted-foreground">{worker.mobile ?? "—"}</TableCell>
      <TableCell>
        <Badge
          variant={attendanceStatusBadgeVariant(worker.status)}
          className={`font-normal capitalize ${attendanceStatusBadgeClass(worker.status)}`}
        >
          {worker.status}
        </Badge>
      </TableCell>
      <TableCell className="text-sm text-muted-foreground">{worker.source ?? "—"}</TableCell>
      <TableCell>
        <Select
          value=""
          onValueChange={(status) => markMutation.mutate(status as AttendanceStatus)}
          disabled={markMutation.isPending}
        >
          <SelectTrigger className="h-8 w-32 text-xs">
            <SelectValue placeholder="Override..." />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="present">Present</SelectItem>
            <SelectItem value="absent">Absent</SelectItem>
            <SelectItem value="unreachable">Unreachable</SelectItem>
          </SelectContent>
        </Select>
      </TableCell>
    </TableRow>
  );
}

function LocationDialog({
  runId,
  locationId,
  onOpenChange,
}: {
  runId: string;
  locationId: string;
  onOpenChange: (open: boolean) => void;
}) {
  const detailQuery = useQuery({
    queryKey: ["attendance-location", runId, locationId],
    queryFn: () => apiGet<LocationDetail>(`/api/attendance/runs/${runId}/locations/${locationId}`),
    refetchInterval: 3000,
  });
  const detail = detailQuery.data;

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        {detailQuery.isLoading && <Skeleton className="h-64 w-full" />}
        {detail && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <MapPin className="h-4 w-4 text-muted-foreground" />
                {detail.location_name}
                {detail.region && <Badge variant="outline">{detail.region}</Badge>}
              </DialogTitle>
              <DialogDescription>
                Supervisor: {detail.supervisor_name} ({detail.supervisor_mobile})
              </DialogDescription>
            </DialogHeader>

            <div className="flex flex-col gap-4">
              <CountsStrip counts={detail.counts} />

              {detail.supervisor_call_id && <SupervisorCallPanel callId={detail.supervisor_call_id} />}

              <div className="max-h-80 overflow-y-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Worker</TableHead>
                      <TableHead>Employee ID</TableHead>
                      <TableHead>Mobile</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Source</TableHead>
                      <TableHead>Override</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {detail.workers.map((worker) => (
                      <WorkerRow key={worker.record_id} runId={runId} locationId={locationId} worker={worker} />
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

// --- Heatmap ---

function HeatmapTile({ location, onClick }: { location: LocationAttendanceSummary; onClick: () => void }) {
  const dispatched = location.supervisor_call_status !== null;
  const hasData = dispatched && location.counts.pending < location.counts.total;
  const colorClass = attendanceRateHeatColor(location.counts.rate, hasData);

  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex aspect-square flex-col items-center justify-center gap-0.5 rounded-md p-1.5 text-center transition-transform hover:scale-105 hover:ring-2 hover:ring-ring ${colorClass}`}
      title={`${location.location_name}: ${location.counts.present}/${location.counts.total} present`}
    >
      <span className="w-full truncate text-[10px] font-medium text-white drop-shadow-sm">
        {location.location_name.replace(/^[A-Za-z ]+ /, "")}
      </span>
      <span className="text-xs font-semibold text-white drop-shadow-sm">
        {hasData ? `${Math.round(location.counts.rate * 100)}%` : "…"}
      </span>
    </button>
  );
}

// --- Today tab ---

function TodayTab() {
  const queryClient = useQueryClient();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedLocationId, setSelectedLocationId] = useState<string | null>(null);

  const runsQuery = useQuery({
    queryKey: ["attendance-runs"],
    queryFn: () => apiGet<RunSummary[]>("/api/attendance/runs"),
  });

  const runs = runsQuery.data ?? [];
  const activeRunId = selectedRunId ?? runs[0]?.id ?? null;

  const runQuery = useQuery({
    queryKey: ["attendance-run", activeRunId],
    queryFn: () => apiGet<RunDetail>(`/api/attendance/runs/${activeRunId}`),
    enabled: !!activeRunId,
    refetchInterval: (query) => {
      const locations = query.state.data?.locations ?? [];
      const anyNonTerminal = locations.some(
        (loc) => loc.supervisor_call_status && !TERMINAL_CALL_STATUSES.has(loc.supervisor_call_status),
      );
      const anyPending = (query.state.data?.counts.pending ?? 0) > 0;
      return anyNonTerminal || anyPending ? 2500 : false;
    },
    refetchIntervalInBackground: true,
  });
  const run = runQuery.data;

  const createRunMutation = useMutation({
    mutationFn: () => apiPost<RunDetail>("/api/attendance/runs", {}),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ["attendance-runs"] });
      setSelectedRunId(created.id);
      toast.success(`Run created for ${created.run_date} - ${created.locations.length} location(s) materialized`);
    },
    onError: (error: unknown) => {
      toast.error(error instanceof ApiError ? error.message : "Failed to create run");
    },
  });

  const dispatchMutation = useMutation({
    mutationFn: () => apiPost<DispatchRunResponse>(`/api/attendance/runs/${activeRunId}/dispatch`),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["attendance-run", activeRunId] });
      toast.success(`Dispatched ${result.dispatched} supervisor roll-call(s)`);
    },
    onError: (error: unknown) => {
      toast.error(error instanceof ApiError ? error.message : "Dispatch failed");
    },
  });

  const simulateMutation = useMutation({
    mutationFn: () => apiPost<SimulateMissedCallsResponse>(`/api/attendance/runs/${activeRunId}/simulate-missed-calls`),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["attendance-run", activeRunId] });
      toast.success(`${result.marked_present} worker(s) marked present via missed call`);
    },
    onError: (error: unknown) => {
      toast.error(error instanceof ApiError ? error.message : "Simulation failed");
    },
  });

  const anyDispatched = run?.locations.some((loc) => loc.supervisor_call_status !== null) ?? false;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {runs.length > 0 && (
            <Select value={activeRunId ?? undefined} onValueChange={setSelectedRunId}>
              <SelectTrigger className="w-56">
                <SelectValue placeholder="Select a run" />
              </SelectTrigger>
              <SelectContent>
                {runs.map((r) => (
                  <SelectItem key={r.id} value={r.id}>
                    {r.run_date} - {r.counts.total} worker(s)
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <Button
            type="button"
            variant="secondary"
            onClick={() => createRunMutation.mutate()}
            disabled={createRunMutation.isPending}
          >
            <CalendarCheck className="h-4 w-4" />
            {createRunMutation.isPending ? "Creating..." : "Create run"}
          </Button>
        </div>

        {run && (
          <div className="flex items-center gap-2">
            <Button
              type="button"
              onClick={() => dispatchMutation.mutate()}
              disabled={dispatchMutation.isPending || anyDispatched}
            >
              <RadioTower className="h-4 w-4" />
              {dispatchMutation.isPending ? "Dispatching..." : anyDispatched ? "Dispatched" : "Dispatch roll-call"}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => simulateMutation.mutate()}
              disabled={simulateMutation.isPending}
            >
              {simulateMutation.isPending ? "Simulating..." : "Simulate missed-call window"}
            </Button>
          </div>
        )}
      </div>

      {runsQuery.isLoading && <Skeleton className="h-40 w-full" />}

      {!runsQuery.isLoading && runs.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
            <CalendarCheck className="h-8 w-8 text-muted-foreground" />
            <p className="text-muted-foreground">No attendance runs yet. Create one to dispatch today&apos;s roll-call.</p>
          </CardContent>
        </Card>
      )}

      {run && (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-baseline gap-3 text-base">
                <span className="text-4xl font-semibold tabular-nums">{Math.round(run.counts.rate * 100)}%</span>
                <span className="text-muted-foreground">present today across {run.locations.length} location(s)</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <CountsStrip counts={run.counts} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Location heatmap</CardTitle>
            </CardHeader>
            <CardContent>
              {run.locations.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  No locations in this run yet - seed demo data from the Locations tab.
                </p>
              ) : (
                <div className="grid grid-cols-[repeat(auto-fill,minmax(64px,1fr))] gap-1.5">
                  {run.locations.map((location) => (
                    <HeatmapTile
                      key={location.location_id}
                      location={location}
                      onClick={() => setSelectedLocationId(location.location_id)}
                    />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {run.exceptions.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Exceptions ({run.exceptions.length})</CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Worker</TableHead>
                      <TableHead>Location</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Reason</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {run.exceptions.map((exception) => (
                      <TableRow
                        key={exception.record_id}
                        className="cursor-pointer"
                        onClick={() => setSelectedLocationId(exception.location_id)}
                      >
                        <TableCell className="font-medium">{exception.worker_name}</TableCell>
                        <TableCell className="text-sm text-muted-foreground">{exception.location_name}</TableCell>
                        <TableCell>
                          <Badge
                            variant={attendanceStatusBadgeVariant(exception.status)}
                            className={`font-normal capitalize ${attendanceStatusBadgeClass(exception.status)}`}
                          >
                            {exception.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">{exception.reason ?? "—"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {activeRunId && selectedLocationId && (
        <LocationDialog
          runId={activeRunId}
          locationId={selectedLocationId}
          onOpenChange={(open) => {
            if (!open) setSelectedLocationId(null);
          }}
        />
      )}
    </div>
  );
}

// --- Locations tab ---

function LocationsTab() {
  const queryClient = useQueryClient();

  const locationsQuery = useQuery({
    queryKey: ["attendance-locations"],
    queryFn: () => apiGet<LocationOut[]>("/api/attendance/locations"),
  });

  const seedMutation = useMutation({
    mutationFn: () => apiPost<SeedDemoResponse>("/api/attendance/seed-demo"),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["attendance-locations"] });
      toast.success(`${result.locations} location(s), ${result.workers} worker(s) ready`);
    },
    onError: (error: unknown) => {
      toast.error(error instanceof ApiError ? error.message : "Seeding failed");
    },
  });

  const locations = locationsQuery.data ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {locations.length} location(s), {locations.reduce((sum, l) => sum + l.worker_count, 0)} worker(s)
        </p>
        <Button type="button" onClick={() => seedMutation.mutate()} disabled={seedMutation.isPending}>
          <Sprout className="h-4 w-4" />
          {seedMutation.isPending ? "Seeding..." : "Seed demo data (100 locations)"}
        </Button>
      </div>

      <Card>
        <CardContent className="pt-6">
          {locationsQuery.isLoading && <Skeleton className="h-40 w-full" />}
          {!locationsQuery.isLoading && locations.length === 0 && (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No locations yet. Seed demo data to create ~100 locations and ~1,000 workers.
            </p>
          )}
          {locations.length > 0 && (
            <div className="max-h-[32rem] overflow-y-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Location</TableHead>
                    <TableHead>Region</TableHead>
                    <TableHead>Supervisor</TableHead>
                    <TableHead>Supervisor mobile</TableHead>
                    <TableHead>Workers</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {locations.map((location) => (
                    <TableRow key={location.id}>
                      <TableCell className="font-medium">{location.name}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">{location.region ?? "—"}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">{location.supervisor_name}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">{location.supervisor_mobile}</TableCell>
                      <TableCell>{location.worker_count}</TableCell>
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

// --- Design tab ---

function DesignTab() {
  const docQuery = useQuery({
    queryKey: ["attendance-design-doc"],
    queryFn: () => apiGet<{ content: string }>("/api/attendance/design-doc"),
  });

  return (
    <Card>
      <CardContent className="pt-6">
        {docQuery.isLoading && <Skeleton className="h-96 w-full" />}
        {docQuery.data && (
          <div className="mx-auto max-w-3xl pb-4">
            <Markdown content={docQuery.data.content} />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function AttendancePage() {
  const locationsQuery = useQuery({
    queryKey: ["attendance-locations"],
    queryFn: () => apiGet<LocationOut[]>("/api/attendance/locations"),
  });
  const [tab, setTab] = useState("today");
  const queryClient = useQueryClient();

  const seedMutation = useMutation({
    mutationFn: () => apiPost<SeedDemoResponse>("/api/attendance/seed-demo"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["attendance-locations"] });
      toast.success("Demo data seeded");
    },
    onError: (error: unknown) => {
      toast.error(error instanceof ApiError ? error.message : "Seeding failed");
    },
  });

  const noLocationsYet = !locationsQuery.isLoading && (locationsQuery.data?.length ?? 0) === 0;

  return (
    <div className="flex flex-col gap-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Attendance</h1>
        <p className="text-muted-foreground">
          1,000 workers, 100 locations, zero apps - supervisor roll-calls plus a free missed-call check-in.
        </p>
      </div>

      {noLocationsYet && tab !== "design" && (
        <Card className="border-primary/30 bg-primary/5">
          <CardContent className="flex flex-col items-center gap-3 py-10 text-center">
            <Sprout className="h-8 w-8 text-primary" />
            <p className="text-muted-foreground">No workforce data yet. Seed demo data to get started.</p>
            <Button type="button" onClick={() => seedMutation.mutate()} disabled={seedMutation.isPending}>
              {seedMutation.isPending ? "Seeding..." : "Seed demo data"}
            </Button>
          </CardContent>
        </Card>
      )}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="today">Today</TabsTrigger>
          <TabsTrigger value="locations">Locations</TabsTrigger>
          <TabsTrigger value="design">Design</TabsTrigger>
        </TabsList>
        <TabsContent value="today">
          <TodayTab />
        </TabsContent>
        <TabsContent value="locations">
          <LocationsTab />
        </TabsContent>
        <TabsContent value="design">
          <DesignTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
