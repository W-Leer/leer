
---

```md
# Replay Model

Replay is a core feature of Leer.

It enables:
- debugging
- experimentation
- comparison
- recovery

---

## Concept

A replay creates a **new run** from:
- a previous run
- or a specific step

Replays are tracked in the `replays` table.

---

## Replay Modes

### 1. Full Replay

Re-executes the entire run from the beginning.

Use cases:
- reproduce a bug
- test determinism

---

### 2. Replay From Step

Starts a new run from a specific step.

Uses:
- previous outputs as checkpoints
- skips earlier steps

Use cases:
- debug later stages
- save time

---

### 3. Step Only

Executes a single step in isolation.

Use cases:
- test prompt changes
- debug tool behavior

---

### 4. Fork

Creates a new run with modified configuration.

Examples:
- change model (GPT → Claude)
- modify prompt
- change tool parameters

Use cases:
- experimentation
- optimization

---

## Run Relationships

Each replay creates:

- a new run (`replay_run_id`)
- linked to a source run (`source_run_id`)

Relationships:
- parent_run_id → immediate origin
- root_run_id → original ancestor

This enables:
- replay trees
- branching history
- comparison across versions

---

## Step-Level Replay

Replay can target:
- entire run
- specific step

When replaying from step:
- earlier steps are treated as checkpoints
- system must reuse their outputs

---

## Config Overrides

Replays may override:
- model
- prompt
- parameters
- tool configuration

Overrides are stored as:
- `override_config_artifact_id`

---

## Replay Safety

Not all steps are safe to replay.

Each step includes:
- `is_replayable` flag

Examples of non-replayable:
- external side effects (payments, writes)
- non-idempotent operations

---

## Future Extensions

Replay model will support:
- partial re-execution
- branching workflows
- rollback
- compensation logic

---

## Summary

Replay is not a utility feature.

It is a **core primitive** that enables:
- debugging
- reliability
- experimentation
- execution control