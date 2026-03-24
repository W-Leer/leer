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
  artifacts: unknown[];
}

export interface CompareRunSummary {
  id: string;
  workflow_name: string;
  status: string;
  created_at: string;
}

export interface CompareStepDiff {
  sequence_index: number;
  name_a: string | null;
  name_b: string | null;
  step_type_a: string | null;
  step_type_b: string | null;
  exists_in_a: boolean;
  exists_in_b: boolean;
  status_a: string | null;
  status_b: string | null;
  status_diff: boolean;
  output_summary_a: Record<string, unknown> | null;
  output_summary_b: Record<string, unknown> | null;
  output_diff: boolean;
  error_summary_a: Record<string, unknown> | null;
  error_summary_b: Record<string, unknown> | null;
  error_diff: boolean;
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
