
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

## Project selection

Runs belong to a project (the SDK's `project_slug`). The UI shows one
project at a time.

- The app fetches `GET /v1/projects` once. The list is ordered by most
  recent run.
- The current project is the first that exists of:
  1. `?project=<slug>` in the URL
  2. the last project picked in this browser (`localStorage`)
  3. the most recently active project
- The sidebar shows the current project and lets the user switch. The
  runs list, the compare page's recent runs, and the run selector all use
  it.
- The runs page keeps `?project=` in its URL, so links and back/forward
  keep the project.
- With no projects yet, the runs page explains how to record a first run.

## Homepage

The homepage fetches:

- `GET /v1/projects/{current_project}/runs`

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
- project management (create, rename, delete projects); projects come from ingestion
- artifacts explorer
- replay UI
- diff UI