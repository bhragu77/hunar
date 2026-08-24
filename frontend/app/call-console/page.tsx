"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { apiGet, apiPost, ApiError } from "@/lib/api";
import type { Agent, CallDetail, CallEventSource } from "@/lib/types";
import { TERMINAL_CALL_STATUSES } from "@/lib/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { toast } from "sonner";

const SOURCE_LABEL: Record<CallEventSource, string> = {
  webhook: "Webhook",
  poll: "Poller",
  mock: "Mock (internal)",
};

function formatTime(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString();
}

function statusVariant(status: string): "default" | "secondary" | "destructive" {
  if (status === "COMPLETED") return "default";
  if (status === "FAILED" || status === "CANCELLED") return "destructive";
  return "secondary";
}

export default function CallConsolePage() {
  const queryClient = useQueryClient();

  const [selectedAgentId, setSelectedAgentId] = useState<string>("");
  const [calleeName, setCalleeName] = useState("");
  const [mobileNumber, setMobileNumber] = useState("");
  const [customData, setCustomData] = useState<Record<string, string>>({});
  const [activeCallId, setActiveCallId] = useState<string | null>(null);

  const agentsQuery = useQuery({
    queryKey: ["agents"],
    queryFn: () => apiGet<Agent[]>("/api/agents"),
  });

  const selectedAgent = useMemo(
    () => agentsQuery.data?.find((agent) => agent.id === selectedAgentId) ?? null,
    [agentsQuery.data, selectedAgentId],
  );

  const callQuery = useQuery({
    queryKey: ["call", activeCallId],
    queryFn: () => apiGet<CallDetail>(`/api/calls/${activeCallId}`),
    enabled: activeCallId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.call.status;
      if (status && TERMINAL_CALL_STATUSES.has(status)) return false;
      return 2000;
    },
    // This is a dev debugging tool people often leave in a background tab while a call
    // plays out - keep polling even when the tab isn't focused/visible.
    refetchIntervalInBackground: true,
  });

  const createCallMutation = useMutation({
    mutationFn: () => {
      const parsedCustomData: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(customData)) {
        const hint = selectedAgent?.custom_variables[key];
        parsedCustomData[key] = hint === "number" ? Number(value) : value;
      }
      return apiPost<{ id: string }>("/api/calls", {
        agent_id: selectedAgentId,
        callee_name: calleeName,
        mobile_number: mobileNumber,
        custom_data: parsedCustomData,
      });
    },
    onSuccess: (call) => {
      setActiveCallId(call.id);
      queryClient.invalidateQueries({ queryKey: ["call", call.id] });
      toast.success("Call dispatched", { description: `id ${call.id}` });
    },
    onError: (error: unknown) => {
      const message = error instanceof ApiError ? error.message : "Failed to create call";
      toast.error(message);
    },
  });

  function handleAgentChange(agentId: string) {
    setSelectedAgentId(agentId);
    const agent = agentsQuery.data?.find((a) => a.id === agentId);
    const nextCustomData: Record<string, string> = {};
    for (const key of Object.keys(agent?.custom_variables ?? {})) {
      nextCustomData[key] = "";
    }
    setCustomData(nextCustomData);
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    createCallMutation.mutate();
  }

  const call = callQuery.data?.call;
  const events = callQuery.data?.events ?? [];

  return (
    <div className="flex flex-col gap-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Call Console (dev)</h1>
        <p className="text-muted-foreground">
          Dispatch a call against the voice core directly and watch it converge to a result -
          the fastest way to see the pipeline work end to end with VOICE_PROVIDER=mock.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Dispatch a call</CardTitle>
            <CardDescription>Picks an agent, then POSTs to /api/calls.</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
              <div className="flex flex-col gap-2">
                <Label htmlFor="agent">Agent</Label>
                {agentsQuery.isLoading ? (
                  <Skeleton className="h-9 w-full" />
                ) : (
                  <Select value={selectedAgentId} onValueChange={handleAgentChange}>
                    <SelectTrigger id="agent" className="w-full">
                      <SelectValue placeholder="Select an agent" />
                    </SelectTrigger>
                    <SelectContent>
                      {agentsQuery.data?.map((agent) => (
                        <SelectItem key={agent.id} value={agent.id}>
                          {agent.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor="callee_name">Callee name</Label>
                <Input
                  id="callee_name"
                  value={calleeName}
                  onChange={(e) => setCalleeName(e.target.value)}
                  placeholder="Jane Doe"
                  required
                />
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor="mobile_number">Mobile number</Label>
                <Input
                  id="mobile_number"
                  value={mobileNumber}
                  onChange={(e) => setMobileNumber(e.target.value)}
                  placeholder="+15551234567"
                  required
                />
              </div>

              {selectedAgent && Object.keys(selectedAgent.custom_variables).length > 0 && (
                <div className="flex flex-col gap-3 rounded-md border p-3">
                  <p className="text-sm font-medium">Custom data for {selectedAgent.name}</p>
                  {Object.entries(selectedAgent.custom_variables).map(([key, hint]) => (
                    <div key={key} className="flex flex-col gap-2">
                      <Label htmlFor={`custom_${key}`}>
                        {key} <span className="text-muted-foreground">({String(hint)})</span>
                      </Label>
                      <Input
                        id={`custom_${key}`}
                        type={hint === "number" ? "number" : "text"}
                        value={customData[key] ?? ""}
                        onChange={(e) => setCustomData((prev) => ({ ...prev, [key]: e.target.value }))}
                      />
                    </div>
                  ))}
                </div>
              )}

              <Button type="submit" disabled={!selectedAgentId || createCallMutation.isPending}>
                {createCallMutation.isPending ? "Dispatching..." : "Dispatch call"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Live call</CardTitle>
            <CardDescription>
              Polls GET /api/calls/{"{id}"} every 2s until the call reaches a terminal status.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!activeCallId && <p className="text-sm text-muted-foreground">Dispatch a call to see it here.</p>}

            {activeCallId && callQuery.isLoading && <Skeleton className="h-40 w-full" />}

            {call && (
              <div className="flex flex-col gap-4">
                <div className="flex items-center gap-2">
                  <Badge variant={statusVariant(call.status)}>{call.status}</Badge>
                  {call.duration_seconds !== null && (
                    <span className="text-sm text-muted-foreground">{call.duration_seconds}s</span>
                  )}
                </div>

                <div>
                  <p className="mb-1 text-sm font-medium">Timeline</p>
                  <ol className="flex flex-col gap-1">
                    {events.map((event) => (
                      <li key={event.id} className="flex items-center gap-2 text-sm">
                        <span className="text-muted-foreground">{formatTime(event.received_at)}</span>
                        <Badge variant="outline">{SOURCE_LABEL[event.source]}</Badge>
                        <span>{event.event_type}</span>
                      </li>
                    ))}
                    {events.length === 0 && (
                      <li className="text-sm text-muted-foreground">No updates yet.</li>
                    )}
                  </ol>
                </div>

                {call.recording_url && (
                  <div>
                    <p className="mb-1 text-sm font-medium">Recording</p>
                    <a
                      href={call.recording_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-sm text-primary underline"
                    >
                      {call.recording_url}
                    </a>
                  </div>
                )}

                {call.result && (
                  <div>
                    <p className="mb-1 text-sm font-medium">Result</p>
                    <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">
                      {JSON.stringify(call.result, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
