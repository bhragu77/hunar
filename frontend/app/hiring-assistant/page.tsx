"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { apiGet, apiPost, ApiError } from "@/lib/api";
import type { Agent, InterviewSummary } from "@/lib/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Users } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

function FunnelStrip({ funnel }: { funnel: InterviewSummary["funnel"] }) {
  const entries = Object.entries(funnel.by_status);
  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">No candidates yet.</p>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {entries.map(([status, count]) => (
        <Badge key={status} variant="secondary" className="font-normal">
          {status}: {count}
        </Badge>
      ))}
    </div>
  );
}

function NewInterviewDialog({ agents }: { agents: Agent[] | undefined }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [agentId, setAgentId] = useState("");

  const createMutation = useMutation({
    mutationFn: () => apiPost<InterviewSummary>("/api/hiring/interviews", { title, description, agent_id: agentId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["interviews"] });
      toast.success("Interview created");
      setOpen(false);
      setTitle("");
      setDescription("");
      setAgentId("");
    },
    onError: (error: unknown) => {
      toast.error(error instanceof ApiError ? error.message : "Failed to create interview");
    },
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="h-4 w-4" />
          New interview
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New interview</DialogTitle>
          <DialogDescription>Creates an interview round backed by a voice agent.</DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            createMutation.mutate();
          }}
        >
          <div className="flex flex-col gap-2">
            <Label htmlFor="title">Role / interview title</Label>
            <Input id="title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Backend Engineer" required />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="description">Job description / evaluation criteria</Label>
            <Textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What should the AI scorecard weigh most heavily?"
              rows={4}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="agent">Voice agent</Label>
            <Select value={agentId} onValueChange={setAgentId}>
              <SelectTrigger id="agent" className="w-full">
                <SelectValue placeholder="Select an agent" />
              </SelectTrigger>
              <SelectContent>
                {agents?.map((agent) => (
                  <SelectItem key={agent.id} value={agent.id}>
                    {agent.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button type="submit" disabled={!title || !agentId || createMutation.isPending}>
              {createMutation.isPending ? "Creating..." : "Create interview"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default function HiringAssistantPage() {
  const interviewsQuery = useQuery({
    queryKey: ["interviews"],
    queryFn: () => apiGet<InterviewSummary[]>("/api/hiring/interviews"),
  });
  const agentsQuery = useQuery({
    queryKey: ["agents"],
    queryFn: () => apiGet<Agent[]>("/api/agents"),
  });

  return (
    <div className="flex flex-col gap-6 p-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Hiring Assistant</h1>
          <p className="text-muted-foreground">
            Create an interview, add candidates, and dispatch AI voice screens for each one.
          </p>
        </div>
        <NewInterviewDialog agents={agentsQuery.data} />
      </div>

      {interviewsQuery.isLoading && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-40 w-full" />
          ))}
        </div>
      )}

      {interviewsQuery.data && interviewsQuery.data.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
            <Users className="h-8 w-8 text-muted-foreground" />
            <p className="text-muted-foreground">No interviews yet. Create one to get started.</p>
          </CardContent>
        </Card>
      )}

      {interviewsQuery.data && interviewsQuery.data.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {interviewsQuery.data.map((interview) => (
            <Link key={interview.id} href={`/hiring-assistant/${interview.id}`}>
              <Card className="h-full transition-colors hover:border-primary/50">
                <CardHeader>
                  <CardTitle>{interview.title}</CardTitle>
                  <CardDescription className="line-clamp-2">
                    {interview.description || "No description provided."}
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex flex-col gap-2">
                  <p className="text-sm text-muted-foreground">{interview.funnel.total} candidate(s)</p>
                  <FunnelStrip funnel={interview.funnel} />
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
