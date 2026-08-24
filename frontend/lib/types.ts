export type Agent = {
  id: string;
  name: string;
  voice_persona: string;
  language: string;
  custom_variables: Record<string, unknown>;
  result_schema: Record<string, unknown>;
};

export type Module = "hiring" | "outreach" | "attendance";

export type Campaign = {
  id: string;
  name: string;
  module: Module;
  agent_id: string;
  result_schema: Record<string, unknown>;
  status: string;
  meta: Record<string, unknown>;
  created_at: string;
};

export type Call = {
  id: string;
  campaign_id: string | null;
  request_id: string;
  provider_call_id: string | null;
  callee_name: string;
  mobile_number: string;
  custom_data: Record<string, unknown>;
  status: string;
  lifecycle_status: string | null;
  engagement_status: string | null;
  answered_by: string | null;
  call_ended_by: string | null;
  recording_url: string | null;
  result: Record<string, unknown> | null;
  transcript: string | null;
  duration_seconds: number | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  ended_at: string | null;
  last_polled_at: string | null;
};

export type CallEventSource = "webhook" | "poll" | "mock";

export type CallEvent = {
  id: number;
  call_id: string;
  event_type: string;
  source: CallEventSource;
  payload: Record<string, unknown>;
  received_at: string;
};

export type CallDetail = {
  call: Call;
  events: CallEvent[];
};

export const TERMINAL_CALL_STATUSES = new Set(["COMPLETED", "FAILED", "CANCELLED"]);
