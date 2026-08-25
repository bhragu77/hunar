import { NextResponse } from "next/server";

import { auth } from "@/auth";

// This runs server-side, inside whatever container/runtime hosts the frontend - NOT in the
// browser. NEXT_PUBLIC_API_URL is the browser-facing URL (e.g. http://localhost:8010 on the
// host, unreachable as "localhost" from *inside* the frontend's own Docker container). Prefer
// INTERNAL_API_URL when set (docker-compose sets it to the backend's container-network
// address, http://backend:8000); everywhere else - native dev, Vercel+Render - the two URLs
// are the same, so falling back to NEXT_PUBLIC_API_URL is correct.
const API_URL = process.env.INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8010";
const INTERNAL_API_TOKEN = process.env.INTERNAL_API_TOKEN ?? "dev-internal-token-change-me";

/**
 * Same-origin proxy to the backend's voice-provider setting. The browser never talks to the
 * backend directly for this - GET is just a passthrough (which mode is active isn't secret),
 * but POST is the actual trust boundary: this route checks the visitor's NextAuth session
 * server-side and rejects guests *before* forwarding to the backend with INTERNAL_API_TOKEN,
 * a shared secret the browser never sees. Without this, "guests can't enable real calls"
 * would only be a frontend UI nicety - see backend's INTERNAL_API_TOKEN docstring.
 */
export async function GET() {
  const response = await fetch(`${API_URL}/api/settings/voice-provider`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  const body = await response.text();
  return new NextResponse(body, {
    status: response.status,
    headers: { "Content-Type": "application/json" },
  });
}

export async function POST(request: Request) {
  const session = await auth();
  if (!session || session.user.role === "guest") {
    return NextResponse.json(
      { detail: "Sign in with Google to change the voice provider" },
      { status: 403 },
    );
  }

  const body = await request.text();
  const response = await fetch(`${API_URL}/api/settings/voice-provider`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Internal-Token": INTERNAL_API_TOKEN,
    },
    body,
  });
  const responseBody = await response.text();
  return new NextResponse(responseBody, {
    status: response.status,
    headers: { "Content-Type": "application/json" },
  });
}
