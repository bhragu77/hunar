"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiGet } from "@/lib/api";
import { outreachBucketBadgeClass, outreachBucketBadgeVariant } from "@/lib/badges";
import type { OutreachOverview } from "@/lib/types";
import { useQuery } from "@tanstack/react-query";
import { Send } from "lucide-react";
import Link from "next/link";

export default function OutreachOverviewPage() {
  const overviewQuery = useQuery({
    queryKey: ["outreach-overview"],
    queryFn: () => apiGet<OutreachOverview>("/api/outreach/overview"),
    refetchInterval: 5000,
    refetchIntervalInBackground: true,
  });

  const overview = overviewQuery.data;

  return (
    <div className="flex flex-col gap-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Outreach</h1>
        <p className="text-muted-foreground">
          Aggregate reachout funnel across every campaign. Manage individual campaigns from People Search.
        </p>
      </div>

      {overviewQuery.isLoading && <Skeleton className="h-40 w-full" />}

      {overview && (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Totals across {overview.campaigns.length} campaign(s) - {overview.total_candidates} candidate(s) sourced
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              {Object.entries(overview.totals).map(([bucket, count]) => (
                <Badge
                  key={bucket}
                  variant={outreachBucketBadgeVariant(bucket)}
                  className={`px-3 py-1 text-sm font-normal ${outreachBucketBadgeClass(bucket)}`}
                >
                  {bucket}: {count}
                </Badge>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              {overview.campaigns.length === 0 && (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  No outreach campaigns yet. Create one from People Search.
                </p>
              )}
              {overview.campaigns.length > 0 && (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Campaign</TableHead>
                        <TableHead>Sourced</TableHead>
                        <TableHead>Interested</TableHead>
                        <TableHead>Not interested</TableHead>
                        <TableHead>Follow-up</TableHead>
                        <TableHead>No response</TableHead>
                        <TableHead>Agent</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {overview.campaigns.map((campaign) => (
                        <TableRow key={campaign.id}>
                          <TableCell className="font-medium">
                            <Link href={`/people-search/${campaign.id}`} className="flex items-center gap-1.5 hover:underline">
                              <Send className="h-3.5 w-3.5 text-muted-foreground" />
                              {campaign.title}
                            </Link>
                          </TableCell>
                          <TableCell>{campaign.funnel.total}</TableCell>
                          <TableCell>{campaign.funnel.counts["Interested"] ?? 0}</TableCell>
                          <TableCell>{campaign.funnel.counts["Not interested"] ?? 0}</TableCell>
                          <TableCell>{campaign.funnel.counts["Follow-up required"] ?? 0}</TableCell>
                          <TableCell>{campaign.funnel.counts["No response"] ?? 0}</TableCell>
                          <TableCell>
                            {campaign.agent_id ? (
                              <Badge variant="secondary" className="font-normal">
                                Set
                              </Badge>
                            ) : (
                              <Badge variant="destructive" className="font-normal">
                                Missing
                              </Badge>
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
