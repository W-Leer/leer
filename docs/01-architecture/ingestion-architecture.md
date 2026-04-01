# Leer — Future-Proof Ingestion Architecture

## Principle
Start simple (FastAPI + Postgres + Blob storage), but design so you can scale to queues, analytics, and search without rewriting the product.

## Core Layers

### 1. SDK Layer
- Captures Runs → Steps → Events → Artifacts
- Batching + retry
- JSON-safe structured payloads

### 2. Ingestion API (FastAPI)
- Auth + validation
- Minimal processing
- Fast write + ACK
- NEVER do heavy work here

### 3. Storage (Canonical)
- Postgres → metadata (runs, steps, summaries)
- Blob storage → large payloads (LLM outputs, files, tool data)

### 4. Async Processing (Future)
- Queue (RabbitMQ first)
- Workers:
  - indexing
  - aggregation
  - enrichment
  - replay prep

### 5. Derived Stores (Later)
- ClickHouse → analytics
- Quickwit → search

## Key Rules
- Never couple ingestion with analytics
- Never block ingestion
- Store raw + structured
- Design for billions of events, build for millions

## Migration Path
1. Today → FastAPI + Postgres
2. Add queue → async processing
3. Add ClickHouse → analytics
4. Add search engine → log search
