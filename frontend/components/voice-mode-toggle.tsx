"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import { toast } from "sonner";

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import type { VoiceProviderState } from "@/lib/types";

// Same-origin proxy (app/api/voice-provider/route.ts), not the external backend directly -
// POST there is session-checked server-side before it's ever forwarded. See that route's
// docstring for why this can't just be apiGet/apiPost against NEXT_PUBLIC_API_URL.
async function fetchVoiceProvider(): Promise<VoiceProviderState> {
  const response = await fetch("/api/voice-provider");
  if (!response.ok) throw new Error("Failed to load voice provider state");
  return response.json();
}

async function updateVoiceProvider(provider: "mock" | "hunar"): Promise<VoiceProviderState> {
  const response = await fetch("/api/voice-provider", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider }),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail ?? "Failed to change voice provider");
  return body;
}

/**
 * Mock/Real switch for the whole deployed backend (see backend's app/core/runtime_state.py -
 * it's one process-wide toggle, not a per-user preference). Real is gated to signed-in
 * (non-guest) users here in the UI; the backend independently refuses to switch to "hunar" at
 * all if HUNAR_API_KEY isn't configured, so this can never silently no-op into a broken state.
 */
export function VoiceModeToggle() {
  const { data: session, status: sessionStatus } = useSession();
  // Fail safe, not open: until we positively know this is a signed-in non-guest session,
  // treat it as guest. sessionStatus can still be "loading" here even after stateQuery has
  // already resolved (the two fetches race independently on mount) - defaulting isGuest to
  // false in that window would let a guest's early click enable real calls before the guest
  // check ever caught up.
  const isGuest = sessionStatus !== "authenticated" || session?.user?.role === "guest";
  const queryClient = useQueryClient();

  const stateQuery = useQuery({
    queryKey: ["voice-provider"],
    queryFn: fetchVoiceProvider,
    refetchInterval: 15_000,
  });

  const mutation = useMutation({
    mutationFn: updateVoiceProvider,
    onSuccess: (result) => {
      queryClient.setQueryData(["voice-provider"], result);
      toast.success(result.provider === "hunar" ? "Real calls enabled" : "Switched to mock calls");
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "Couldn't change voice mode");
    },
  });

  if (!stateQuery.data) {
    return null;
  }

  const { provider, hunar_configured } = stateQuery.data;
  const realDisabled = isGuest || !hunar_configured;

  return (
    <div>
      <Tabs
        value={provider}
        onValueChange={(value) => {
          if (value === provider || mutation.isPending) return;
          if (value === "hunar" && realDisabled) return;
          mutation.mutate(value as "mock" | "hunar");
        }}
      >
        <TabsList className="w-full">
          <TabsTrigger value="mock" className="flex-1">
            Mock
          </TabsTrigger>
          <TabsTrigger
            value="hunar"
            disabled={realDisabled}
            title={
              isGuest
                ? "Sign in with Google to enable real calls"
                : !hunar_configured
                  ? "HUNAR_API_KEY isn't configured on this backend"
                  : undefined
            }
            className={cn("flex-1", realDisabled && "opacity-50")}
          >
            Real
          </TabsTrigger>
        </TabsList>
      </Tabs>
      {provider === "hunar" && (
        <p className="px-1 pt-1.5 text-xs text-muted-foreground">
          Live - calls placed now are real and cost money.
        </p>
      )}
    </div>
  );
}
