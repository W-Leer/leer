export interface ProjectSummary {
  id: string;
  name: string;
  slug: string;
}

export interface RunListItem {
  id: string;
  workflow_name: string;
  status: string;
  source: string | null;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
  total_steps: number;
  completed_steps: number;
  failed_steps: number;
  total_duration_ms: number | null;
  model_provider: string | null;
  model_name: string | null;
  output_summary: Record<string, unknown> | null;
}

export interface ProjectRunsResponse {
  project: ProjectSummary;
  runs: RunListItem[];
  total_count: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface TimelineRun {
  id: string;
  workflow_name: string;
  status: string;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
  output_summary: Record<string, unknown> | null;
  error_summary: Record<string, unknown> | null;
  total_steps: number;
  completed_steps: number;
  failed_steps: number;
  total_duration_ms: number | null;
}

export interface StepArtifactRef {
  id: string;
  kind: string;
  role: string | null;
  format: string | null;
  preview_text: string | null;
  sequence_index: number | null;
  inline_data?: Record<string, unknown> | null;
}

export interface LLMShape {
  provider: string;
  model: string | null;
  input: {
    system: string | null;
    messages: Record<string, unknown>[];
    tools: Record<string, unknown>[];
    params: Record<string, unknown>;
  };
  output: {
    text: string | null;
    tool_calls: Record<string, unknown>[];
    content_blocks: Record<string, unknown>[];
  };
  usage: {
    prompt_tokens: number | null;
    completion_tokens: number | null;
    total_tokens: number | null;
  };
  meta: {
    finish_reason: string | null;
    request_id: string | null;
    latency_ms: number | null;
  };
}

export interface TimelineStep {
  id: string;
  parent_step_id: string | null;
  sequence_index: number;
  name: string;
  step_type: string;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  input_summary: Record<string, unknown> | null;
  output_summary: Record<string, unknown> | null;
  error_summary: Record<string, unknown> | null;
  metadata: Record<string, unknown>;

  model_provider: string | null;
  model_name: string | null;
  duration_ms: number | null;

  llm: LLMShape | null;
  artifacts: StepArtifactRef[];
}

export interface TimelineEvent {
  id: string;
  step_id: string | null;
  event_type: string;
  sequence_index: number;
  timestamp: string;
  payload: Record<string, unknown>;
}

export interface TimelineResponse {
  run: TimelineRun;
  steps: TimelineStep[];
  events: TimelineEvent[];
  artifacts: StepArtifactRef[];
}

export interface CompareRunSummary {
  id: string;
  workflow_name: string;
  status: string;
  created_at: string;
  total_steps: number;
  total_duration_ms: number | null;
}

export interface CompareStepDiff {
  match_kind: "exact_name" | "fallback_type_index" | "missing";
  exists_in_a: boolean;
  exists_in_b: boolean;

  sequence_index_a: number | null;
  sequence_index_b: number | null;

  parent_step_id_a: string | null;
  parent_step_id_b: string | null;

  name_a: string | null;
  name_b: string | null;
  step_type_a: string | null;
  step_type_b: string | null;

  status_a: string | null;
  status_b: string | null;
  status_diff: boolean;

  input_summary_a: Record<string, unknown> | null;
  input_summary_b: Record<string, unknown> | null;
  input_diff: boolean;

  output_summary_a: Record<string, unknown> | null;
  output_summary_b: Record<string, unknown> | null;
  output_diff: boolean;

  error_summary_a: Record<string, unknown> | null;
  error_summary_b: Record<string, unknown> | null;
  error_diff: boolean;

  duration_ms_a: number | null;
  duration_ms_b: number | null;

  model_provider_a: string | null;
  model_provider_b: string | null;

  model_name_a: string | null;
  model_name_b: string | null;

  metadata_a: Record<string, unknown> | null;
  metadata_b: Record<string, unknown> | null;

  llm_a: LLMShape | null;
  llm_b: LLMShape | null;
}

export interface CompareRunDiff {
  status_a: string;
  status_b: string;
  status_diff: boolean;
  output_summary_a: Record<string, unknown> | null;
  output_summary_b: Record<string, unknown> | null;
  output_diff: boolean;
  error_summary_a: Record<string, unknown> | null;
  error_summary_b: Record<string, unknown> | null;
  error_diff: boolean;
}

export interface CompareResponse {
  run_a: CompareRunSummary;
  run_b: CompareRunSummary;
  run_diff: CompareRunDiff;
  steps: CompareStepDiff[];
}
