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
