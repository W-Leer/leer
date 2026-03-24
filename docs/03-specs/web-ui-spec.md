
```md
# Web UI Spec

This document defines the first tiny UI for Leer.

---

## Goals

The UI should let a user:

- see recent runs
- click a run
- inspect its timeline

The UI is for MVP clarity, not design polish.

---

## Stack

- Next.js
- TypeScript

Keep styling simple.

---

## Pages

- `/` → recent runs list
- `/runs/[id]` → run detail timeline

---

## Homepage

The homepage fetches:

- `GET /v1/projects/demo-project/runs`

### Display

For each run card show:

- workflow name
- status
- created at
- total steps
- duration
- output preview if present

### Interaction

- clicking a run card goes to `/runs/{id}`

---

## Run Detail Page

The run detail page fetches:

- `GET /v1/runs/{run_id}/timeline`

### Display sections

#### Run Header
Show:
- workflow name
- status
- created at
- started at
- ended at
- duration
- output summary
- error summary if present

#### Timeline
Show steps in vertical order.

For each step show:
- step name
- step type
- status
- sequence index
- started/ended time
- output summary
- error summary if present

#### Events
For MVP, events can be shown in a simple list below the steps.

---

## Design Principles

- prioritize clarity over design complexity
- no auth
- no filtering
- no pagination
- no charts
- no replay controls yet

---

## Non-goals

Do not implement:
- dark mode
- search
- advanced timeline visualization
- multi-project support in UI
- artifacts explorer
- replay UI
- diff UI