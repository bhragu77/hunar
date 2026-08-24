import type { Recommendation } from "@/lib/types";

const TERMINAL_FAILURE = new Set(["FAILED", "CANCELLED"]);

/** shadcn Badge variant for a call/candidate status. */
export function statusBadgeVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "COMPLETED") return "default";
  if (TERMINAL_FAILURE.has(status)) return "destructive";
  return "secondary";
}

/** Extra classes layered on top of the badge variant for a recommendation - shadcn's Badge
 * only ships default/secondary/destructive/outline, and "advance" reads much clearer as
 * green than as the default foreground color. */
export function recommendationBadgeClass(recommendation: Recommendation | null): string {
  switch (recommendation) {
    case "advance":
      return "border-transparent bg-emerald-600 text-white dark:bg-emerald-500";
    case "hold":
      return "border-transparent bg-amber-500 text-white dark:bg-amber-600";
    case "reject":
      return ""; // falls back to the Badge's own destructive variant
    default:
      return "";
  }
}

/** Extra classes layered on top of the badge variant for an outreach funnel bucket - same
 * approach as recommendationBadgeClass, so bucket colors read consistently with the rest of
 * the app's status coloring. */
export function outreachBucketBadgeClass(bucket: string): string {
  switch (bucket) {
    case "Interested":
      return "border-transparent bg-emerald-600 text-white dark:bg-emerald-500";
    case "Follow-up required":
      return "border-transparent bg-amber-500 text-white dark:bg-amber-600";
    case "Not interested":
    case "No response":
      return ""; // falls back to the Badge's own destructive variant
    case "Contacting":
      return "border-transparent bg-blue-600 text-white dark:bg-blue-500";
    default:
      return "";
  }
}

export function outreachBucketBadgeVariant(bucket: string): "default" | "secondary" | "destructive" | "outline" {
  if (bucket === "Not interested" || bucket === "No response") return "destructive";
  if (bucket === "Sourced") return "outline";
  return "secondary";
}

/** shadcn Badge variant for an attendance status. */
export function attendanceStatusBadgeVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "present") return "default";
  if (status === "absent" || status === "unreachable") return "destructive";
  return "outline"; // pending
}

/** Extra classes layered on top of the badge variant, same approach as
 * recommendationBadgeClass - "present" reads much clearer as green than the default
 * foreground color, and "unreachable" is a distinct amber from a plain "absent". */
export function attendanceStatusBadgeClass(status: string): string {
  switch (status) {
    case "present":
      return "border-transparent bg-emerald-600 text-white dark:bg-emerald-500";
    case "unreachable":
      return "border-transparent bg-amber-500 text-white dark:bg-amber-600";
    case "absent":
      return ""; // falls back to the Badge's own destructive variant
    default:
      return ""; // pending
  }
}

/** Background color for a heatmap tile, scaled by attendance rate (0-1). Distinct from the
 * badge classes above since a tile needs a continuous scale, not a discrete per-status color. */
export function attendanceRateHeatColor(rate: number, hasData: boolean): string {
  if (!hasData) return "bg-muted";
  if (rate >= 0.9) return "bg-emerald-600 dark:bg-emerald-500";
  if (rate >= 0.75) return "bg-emerald-500/70 dark:bg-emerald-600/70";
  if (rate >= 0.5) return "bg-amber-500 dark:bg-amber-600";
  return "bg-destructive";
}

export function postCallStatusLabel(status: string): string {
  switch (status) {
    case "done":
      return "Ready";
    case "pending":
      return "Pending";
    case "failed":
      return "Failed";
    case "skipped":
      return "Skipped";
    default:
      return status;
  }
}
