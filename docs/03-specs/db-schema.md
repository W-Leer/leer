# DB Schema (Postgres)

This document defines the core database schema for Leer.

---

## Tables

- projects
- runs
- steps
- events
- artifacts
- replays

---

## projects

```sql
CREATE TABLE projects (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## runs

```sql
CREATE TABLE runs (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    external_id TEXT,
    workflow_name TEXT NOT NULL,
    trigger_type TEXT NOT NULL DEFAULT 'manual',
    source TEXT,

    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'paused', 'completed', 'failed', 'cancelled')),

    parent_run_id UUID REFERENCES runs(id) ON DELETE SET NULL,
    root_run_id UUID REFERENCES runs(id) ON DELETE SET NULL,

    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    input_summary JSONB,
    output_summary JSONB,
    error_summary JSONB,

    model_provider TEXT,
    model_name TEXT,

    total_steps INT NOT NULL DEFAULT 0,
    completed_steps INT NOT NULL DEFAULT 0,
    failed_steps INT NOT NULL DEFAULT 0,

    total_tokens_input INT,
    total_tokens_output INT,
    total_cost_usd NUMERIC(12,6),
    total_duration_ms INT,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb
);
```

---

## steps

```sql
CREATE TABLE steps (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,

    parent_step_id UUID REFERENCES steps(id) ON DELETE SET NULL,

    sequence_index INT NOT NULL,
    name TEXT NOT NULL,
    step_type TEXT NOT NULL CHECK (step_type IN ('llm', 'tool', 'code', 'router', 'human', 'memory', 'system')),

    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'paused', 'completed', 'failed', 'skipped', 'cancelled')),

    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,

    input_summary JSONB,
    output_summary JSONB,
    error_summary JSONB,

    input_artifact_id UUID,
    output_artifact_id UUID,
    config_artifact_id UUID,

    checkpoint_key TEXT,
    is_replayable BOOLEAN NOT NULL DEFAULT TRUE,

    retry_count INT NOT NULL DEFAULT 0,
    duration_ms INT,

    model_provider TEXT,
    model_name TEXT,

    token_input INT,
    token_output INT,
    cost_usd NUMERIC(12,6),

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
```

---

## events

```sql
CREATE TABLE events (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    step_id UUID REFERENCES steps(id) ON DELETE CASCADE,

    event_type TEXT NOT NULL,
    sequence_index INT NOT NULL,

    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);
```

---

## artifacts

```sql
CREATE TABLE artifacts (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    run_id UUID REFERENCES runs(id) ON DELETE CASCADE,
    step_id UUID REFERENCES steps(id) ON DELETE CASCADE,

    artifact_type TEXT NOT NULL,
    storage_kind TEXT NOT NULL CHECK (storage_kind IN ('inline', 'blob')),

    mime_type TEXT,
    size_bytes BIGINT,

    inline_data JSONB,
    blob_path TEXT,

    sha256 TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
```

---

## replays

```sql
CREATE TABLE replays (
    id UUID PRIMARY KEY,

    source_run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    source_step_id UUID REFERENCES steps(id) ON DELETE SET NULL,
    replay_run_id UUID NOT NULL UNIQUE REFERENCES runs(id) ON DELETE CASCADE,

    replay_mode TEXT NOT NULL CHECK (replay_mode IN ('full', 'from_step', 'step_only', 'fork')),

    override_config_artifact_id UUID,
    reason TEXT,

    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
```

---

## Indexes

```sql
CREATE INDEX idx_runs_project_created_at ON runs(project_id, created_at DESC);
CREATE INDEX idx_runs_root_run_id ON runs(root_run_id);
CREATE INDEX idx_runs_parent_run_id ON runs(parent_run_id);

CREATE INDEX idx_steps_run_sequence ON steps(run_id, sequence_index);
CREATE INDEX idx_steps_parent_step_id ON steps(parent_step_id);

CREATE INDEX idx_events_run_sequence ON events(run_id, sequence_index);
CREATE INDEX idx_events_step_sequence ON events(step_id, sequence_index);

CREATE INDEX idx_artifacts_run_id ON artifacts(run_id);
CREATE INDEX idx_artifacts_step_id ON artifacts(step_id);

CREATE INDEX idx_replays_source_run_id ON replays(source_run_id);
```

---

## Storage Strategy

### Store in Postgres
- metadata
- summaries
- events
- small JSON artifacts

### Store in Blob Storage
- large prompts
- long responses
- files
- heavy tool outputs

### Rule of thumb
- small JSON → inline
- large payload → blob

---

## Notes

- Schema is optimized for observability first
- Supports replay and diffing
- Designed to evolve into execution platform
