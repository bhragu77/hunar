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
  outreach_summary: string | null;
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

// --- People Search & Reachout (Module 2) ---

export type SearchCriteria = {
  titles: string[];
  seniorities: string[];
  skills: string[];
  locations: string[];
  industries: string[];
  min_years: number | null;
  max_years: number | null;
  keywords: string[];
};

export type AgentSpec = {
  name: string;
  voice_persona: string;
  language: string;
  persona_name: string;
  agent_prompt: string;
  objective: string;
  introduction: string;
  result_prompt: string;
  custom_variables: Record<string, unknown>;
  result_schema: Record<string, unknown>;
};

export type OutreachBucket =
  | "Sourced"
  | "Contacting"
  | "No response"
  | "Interested"
  | "Not interested"
  | "Follow-up required"
  | "Contacted";

export const OUTREACH_FUNNEL_BUCKETS: OutreachBucket[] = [
  "Sourced",
  "Contacting",
  "No response",
  "Interested",
  "Not interested",
  "Follow-up required",
  "Contacted",
];

export type OutreachFunnelSummary = {
  total: number;
  counts: Record<string, number>;
};

export type SourcedCandidate = {
  id: string;
  campaign_id: string;
  full_name: string;
  title: string | null;
  company: string | null;
  location: string | null;
  linkedin_url: string | null;
  email: string | null;
  mobile_number: string | null;
  years_experience: number | null;
  match_score: number | null;
  source: string;
  selected: boolean;
  call_id: string | null;
  call_status: string | null;
  bucket: OutreachBucket;
  created_at: string;
};

export type OutreachCampaignSummary = {
  id: string;
  title: string;
  job_description: string | null;
  agent_id: string | null;
  agent_autocreated: boolean;
  agent_create_error: string | null;
  created_at: string;
  funnel: OutreachFunnelSummary;
};

export type OutreachCampaignDetail = {
  id: string;
  title: string;
  job_description: string | null;
  criteria: SearchCriteria;
  agent_id: string | null;
  agent_spec: AgentSpec;
  agent_autocreated: boolean;
  agent_create_error: string | null;
  result_schema: Record<string, unknown>;
  created_at: string;
  funnel: OutreachFunnelSummary;
  candidates: SourcedCandidate[];
};

export type DispatchResult = {
  dispatched: string[];
  skipped_no_phone: string[];
};

export type OutreachOverview = {
  total_candidates: number;
  totals: Record<string, number>;
  campaigns: OutreachCampaignSummary[];
};

// --- Attendance (Module 3) ---

export type AttendanceStatus = "pending" | "present" | "absent" | "unreachable";

export type AttendanceSource = "supervisor_call" | "missed_call" | "manual" | "worker_call";

export const ATTENDANCE_TERMINAL_STATUSES = new Set(["present", "absent", "unreachable"]);

export type SeedDemoResponse = {
  locations: number;
  workers: number;
  created_locations: number;
  created_workers: number;
};

export type LocationOut = {
  id: string;
  name: string;
  region: string | null;
  supervisor_name: string;
  supervisor_mobile: string;
  worker_count: number;
  created_at: string;
};

export type AttendanceCounts = {
  pending: number;
  present: number;
  absent: number;
  unreachable: number;
  total: number;
  rate: number;
};

export type LocationAttendanceSummary = {
  location_id: string;
  location_name: string;
  region: string | null;
  supervisor_call_id: string | null;
  supervisor_call_status: string | null;
  counts: AttendanceCounts;
};

export type ExceptionRecord = {
  record_id: string;
  worker_id: string;
  worker_name: string;
  employee_id: string;
  location_id: string;
  location_name: string;
  status: AttendanceStatus;
  reason: string | null;
};

export type RunSummary = {
  id: string;
  run_date: string;
  status: string;
  created_at: string;
  counts: AttendanceCounts;
};

export type RunDetail = {
  id: string;
  run_date: string;
  status: string;
  created_at: string;
  counts: AttendanceCounts;
  locations: LocationAttendanceSummary[];
  exceptions: ExceptionRecord[];
};

export type WorkerAttendanceOut = {
  record_id: string;
  worker_id: string;
  full_name: string;
  employee_id: string;
  mobile: string | null;
  status: AttendanceStatus;
  source: AttendanceSource | null;
  reason: string | null;
  marked_at: string | null;
};

export type LocationDetail = {
  location_id: string;
  location_name: string;
  region: string | null;
  supervisor_name: string;
  supervisor_mobile: string;
  supervisor_call_id: string | null;
  workers: WorkerAttendanceOut[];
  counts: AttendanceCounts;
};

export type DispatchRunResponse = {
  dispatched: number;
};

export type SimulateMissedCallsResponse = {
  marked_present: number;
};
