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
