"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { apiGet } from "@/lib/api";
import type { Agent } from "@/lib/types";
import { useQuery } from "@tanstack/react-query";
import { CalendarCheck, Mic, Send, Users } from "lucide-react";

const OVERVIEW_CARDS = [
  {
    title: "Hiring Assistant",
    description: "Voice-driven candidate screening calls.",
    icon: Mic,
  },
  {
    title: "People Search",
    description: "Find and enrich candidate profiles.",
    icon: Users,
  },
  {
    title: "Outreach",
    description: "Automated candidate communication.",
    icon: Send,
  },
  {
    title: "Attendance",
    description: "Interview confirmations and reminders.",
    icon: CalendarCheck,
  },
] as const;

function BackendStatusBadge() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["agents"],
    queryFn: () => apiGet<Agent[]>("/api/agents"),
  });

  if (isLoading) {
    return <Skeleton className="h-6 w-40" />;
  }

  if (isError) {
    return <Badge variant="destructive">Backend unreachable</Badge>;
  }

  return (
    <Badge variant="secondary">
      {data?.length ?? 0} voice agent{data?.length === 1 ? "" : "s"} connected
    </Badge>
  );
}

export default function Home() {
  return (
    <div className="flex flex-col gap-6 p-8">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
        <p className="text-muted-foreground">Welcome to Hunar, your hiring automation platform.</p>
        <BackendStatusBadge />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {OVERVIEW_CARDS.map(({ title, description, icon: Icon }) => (
          <Card key={title}>
            <CardHeader>
              <Icon className="mb-2 h-5 w-5 text-muted-foreground" />
              <CardTitle>{title}</CardTitle>
              <CardDescription>{description}</CardDescription>
            </CardHeader>
          </Card>
        ))}
      </div>
    </div>
  );
}
