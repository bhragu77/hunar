const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
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

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new ApiError(response.status, body || `Request to ${path} failed with ${response.status}`);
  }

  return (await response.json()) as T;
}
