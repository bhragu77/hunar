export type Agent = {
  id: string;
  name: string;
  voice_persona: string;
  language: string;
  custom_variables: Record<string, unknown> | string[];
  result_schema: Record<string, unknown>;
};

export type Module = "hiring" | "outreach" | "attendance";

export type Campaign = {
  id: string;
  name: string;
  description: string | null;
  module: Module;
  agent_id: string;
  result_schema: Record<string, unknown>;
  status: string;
  meta: Record<string, unknown>;
  created_at: string;
};

export type PostCallStatus = "pending" | "done" | "failed" | "skipped";

export type Recommendation = "advance" | "hold" | "reject";

export type Competency = {
  name: string;
  score: number;
  notes: string;
};

export type Scorecard = {
  recommendation: Recommendation;
  overall_score: number;
  summary: string;
  strengths: string[];
  concerns: string[];
  competencies: Competency[];
  suggested_followups: string[];
  red_flags: string[];
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
  duration_seconds: number | null;
  transcript: string | null;
  transcript_status: PostCallStatus;
  transcript_error: string | null;
  scorecard: Scorecard | null;
  scorecard_status: PostCallStatus;
  scorecard_error: string | null;
  scorecard_generated_at: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  ended_at: string | null;
  last_polled_at: string | null;
};

export type CallEventSource = "webhook" | "poll" | "mock" | "pipeline";

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

// --- Hiring module ---

export type FunnelSummary = {
  total: number;
  by_status: Record<string, number>;
  by_recommendation: Record<string, number>;
};

export type InterviewSummary = {
  id: string;
  title: string;
  description: string | null;
  agent_id: string;
  created_at: string;
  funnel: FunnelSummary;
};

export type CandidateSummary = {
  id: string;
  callee_name: string;
  mobile_number: string;
  provider_call_id: string | null;
  status: string;
  lifecycle_status: string | null;
  transcript_status: PostCallStatus;
  scorecard_status: PostCallStatus;
  recommendation: Recommendation | null;
  overall_score: number | null;
  created_at: string;
  updated_at: string;
};

export type InterviewDetail = {
  id: string;
  title: string;
  description: string | null;
  agent_id: string;
  result_schema: Record<string, unknown>;
  created_at: string;
  funnel: FunnelSummary;
  candidates: CandidateSummary[];
};
