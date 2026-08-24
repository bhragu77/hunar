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
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { outreachBucketBadgeClass, outreachBucketBadgeVariant } from "@/lib/badges";
import { apiGet, apiPost, ApiError } from "@/lib/api";
import type { OutreachCampaignDetail, OutreachCampaignSummary } from "@/lib/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Search, Users } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

function FunnelStrip({ funnel }: { funnel: OutreachCampaignSummary["funnel"] }) {
  const entries = Object.entries(funnel.counts).filter(([, count]) => count > 0);
  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">No candidates sourced yet.</p>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {entries.map(([bucket, count]) => (
        <Badge
          key={bucket}
          variant={outreachBucketBadgeVariant(bucket)}
          className={`font-normal ${outreachBucketBadgeClass(bucket)}`}
        >
          {bucket}: {count}
        </Badge>
      ))}
    </div>
  );
}

function NewCampaignDialog() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [jobDescription, setJobDescription] = useState("");

  const createMutation = useMutation({
    mutationFn: () =>
      apiPost<OutreachCampaignDetail>("/api/outreach/campaigns", { title, job_description: jobDescription }),
    onSuccess: (campaign) => {
      queryClient.invalidateQueries({ queryKey: ["outreach-campaigns"] });
      toast.success("Campaign created - criteria and outreach agent generated");
      setOpen(false);
      setTitle("");
      setJobDescription("");
      router.push(`/people-search/${campaign.id}`);
    },
    onError: (error: unknown) => {
      toast.error(error instanceof ApiError ? error.message : "Failed to create campaign");
    },
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="h-4 w-4" />
          New reachout campaign
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>New reachout campaign</DialogTitle>
          <DialogDescription>
            Paste a job description - we&apos;ll derive search criteria and design an outreach voice agent for it.
          </DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            createMutation.mutate();
          }}
        >
          <div className="flex flex-col gap-2">
            <Label htmlFor="title">Role title</Label>
            <Input id="title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Senior Backend Engineer" required />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="jd">Job description</Label>
            <Textarea
              id="jd"
              value={jobDescription}
              onChange={(e) => setJobDescription(e.target.value)}
              placeholder="Paste the full job description here..."
              rows={8}
              required
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={!title || !jobDescription || createMutation.isPending}>
              {createMutation.isPending ? "Generating..." : "Create campaign"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default function PeopleSearchPage() {
  const campaignsQuery = useQuery({
    queryKey: ["outreach-campaigns"],
    queryFn: () => apiGet<OutreachCampaignSummary[]>("/api/outreach/campaigns"),
  });

  return (
    <div className="flex flex-col gap-6 p-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">People Search</h1>
          <p className="text-muted-foreground">
            Paste a JD, source candidates, and dispatch AI voice outreach - all in one campaign.
          </p>
        </div>
        <NewCampaignDialog />
      </div>

      {campaignsQuery.isLoading && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-40 w-full" />
          ))}
        </div>
      )}

      {campaignsQuery.data && campaignsQuery.data.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
            <Users className="h-8 w-8 text-muted-foreground" />
            <p className="text-muted-foreground">No reachout campaigns yet. Create one to get started.</p>
          </CardContent>
        </Card>
      )}

      {campaignsQuery.data && campaignsQuery.data.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {campaignsQuery.data.map((campaign) => (
            <Link key={campaign.id} href={`/people-search/${campaign.id}`}>
              <Card className="h-full transition-colors hover:border-primary/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Search className="h-4 w-4 text-muted-foreground" />
                    {campaign.title}
                  </CardTitle>
                  <CardDescription className="line-clamp-2">
                    {campaign.job_description || "No job description provided."}
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex flex-col gap-2">
                  <p className="text-sm text-muted-foreground">{campaign.funnel.total} candidate(s) sourced</p>
                  <FunnelStrip funnel={campaign.funnel} />
                  {!campaign.agent_id && (
                    <Badge variant="destructive" className="w-fit font-normal">
                      Agent not set
                    </Badge>
                  )}
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
