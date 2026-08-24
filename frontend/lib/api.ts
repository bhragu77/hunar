const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8010";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function parseJsonOrThrow<T>(response: Response, path: string): Promise<T> {
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new ApiError(response.status, body || `Request to ${path} failed with ${response.status}`);
  }
  return (await response.json()) as T;
}

/**
 * GET `path` against the backend and parse the response as JSON.
 * The backend base URL comes from NEXT_PUBLIC_API_URL - never put secrets here,
 * this code runs in the browser.
 */
export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  return parseJsonOrThrow<T>(response, path);
}

/**
 * POST `body` as JSON to `path` against the backend and parse the response as JSON.
 */
export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parseJsonOrThrow<T>(response, path);
}
