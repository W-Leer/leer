# Architecture Overview

## Components

- SDK (Python)
- API server (FastAPI)
- Database (Postgres)
- Blob storage
- Web UI

## Flow

User app
→ SDK captures execution
→ API ingests traces
→ DB stores runs + steps
→ UI displays timeline

## Core concepts

- Run
- Step
- Event
- Artifact
- Replay/Fork

## Design principle

System must support:
- replay
- diffing
- future execution control