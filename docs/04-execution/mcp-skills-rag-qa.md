# MCP / Skills / RAG — QA Checklist

Manual QA checklist for verifying MCP, capability, and retrieval tracing
end-to-end in Leer.

---

## A. Setup

| # | Item | Done |
|---|------|------|
| A1 | API running at `http://127.0.0.1:8000` | ☐ |
| A2 | Postgres running with all migrations applied | ☐ |
| A3 | Web UI running at `http://localhost:3000` | ☐ |
| A4 | Run MCP demo: `cd apps/sdk-python && uv run python ../../examples/demo_mcp_tracing.py` | ☐ |
| A5 | Run RAG demo: `cd apps/sdk-python && uv run python ../../examples/demo_rag_tracing.py` | ☐ |
| A6 | Confirm both demos print "Result:" with valid JSON | ☐ |
| A7 | Navigate to project list in UI, find `demo-project` | ☐ |

---

## B. MCP Run-Detail Checks

Open each MCP demo run (`mcp-tracing-demo-a` and `mcp-tracing-demo-b`).

| # | Check | Run A | Run B |
|---|-------|-------|-------|
| B1 | MCP badge (violet) visible on tool steps | ☐ | ☐ |
| B2 | Capability badge (`mcp_tool`, violet) visible on tool steps | ☐ | ☐ |
| B3 | MCP metadata rows visible: server, operation, target, transport, server_id | ☐ | ☐ |
| B4 | Capability metadata rows visible: kind=mcp_tool, name, label | ☐ | ☐ |
| B5 | `mcp_request` artifact in artifact list | ☐ | ☐ |
| B6 | `mcp_response` artifact in artifact list (Run A both steps, Run B query_schema only) | ☐ | ☐ |
| B7 | `mcp_error` artifact in artifact list (Run B, run_query only) | ☐ | ☐ |
| B8 | `tool_request` / `tool_response` auto-generated artifacts present | ☐ | ☐ |
| B9 | Tool lifecycle: exact linkage confidence badge on tool steps | ☐ | ☐ |
| B10 | Click LLM tool call → navigates to tool step | ☐ | ☐ |
| B11 | Click tool step back-link → navigates to source LLM step | ☐ | ☐ |
| B12 | run_query (Run B): failed status badge visible | ☐ | ☐ |
| B13 | MCP artifact payloads render as inspectable JSON in ArtifactViewer | ☐ | ☐ |
| B14 | Server names display correctly: `filesystem-server` (A), `database-server` (B) | ☐ | ☐ |

---

## C. Retrieval Run-Detail Checks

Open each RAG demo run (`rag-tracing-demo-a` and `rag-tracing-demo-b`).

| # | Check | Run A | Run B |
|---|-------|-------|-------|
| C1 | Retrieval badge (teal) visible on vector_search step | ☐ | ☐ |
| C2 | Retrieval stage badge: `composite` | ☐ | ☐ |
| C3 | Capability badge: `retrieval` | ☐ | ☐ |
| C4 | Retrieval metadata rows: backend, index, stage | ☐ | ☐ |
| C5 | `retrieval_request` artifact present and inspectable | ☐ | ☐ |
| C6 | `retrieval_candidates` artifact present (preview: "50 candidates" / "120 candidates") | ☐ | ☐ |
| C7 | `retrieval_rerank` artifact present | ☐ | ☐ |
| C8 | `retrieval_selected` artifact present (preview: "5 selected" / "8 selected") | ☐ | ☐ |
| C9 | `retrieval_context` artifact present and readable as plain text | ☐ | ☐ |
| C10 | `tool_request` / `tool_response` auto-generated artifacts present | ☐ | ☐ |
| C11 | Candidate payload renders as JSON tree in ArtifactViewer (50/120 items) | ☐ | ☐ |
| C12 | No crash or layout issue with 120-candidate payload | ☐ | ☐ |
| C13 | LLM synthesizer step renders normally (no retrieval badges) | ☐ | ☐ |
| C14 | output_summary visible on vector_search with `kind: "retrieval"` | ☐ | ☐ |

---

## D. Compare Checks

### D1. MCP Compare

Navigate to compare page: select `mcp-tracing-demo-a` as Run A and `mcp-tracing-demo-b` as Run B.

| # | Check | Done |
|---|-------|------|
| D1.1 | MCP compare section visible on aligned tool steps | ☐ |
| D1.2 | Server diff: `filesystem-server` → `database-server` highlighted | ☐ |
| D1.3 | Transport diff: `stdio` → `http` highlighted | ☐ |
| D1.4 | Operation diff or matching: `tool_call` on both sides | ☐ |
| D1.5 | MCP badge on both sides in step header | ☐ |
| D1.6 | Capability badge (`mcp_tool`) on both sides | ☐ |
| D1.7 | Capability compare section: kind=mcp_tool on both sides | ☐ |
| D1.8 | Tool linkage section still visible (provider, model) | ☐ |
| D1.9 | Insight block: MCP server divergence message appears | ☐ |
| D1.10 | Tool call name differences visible (read_file vs query_schema, etc.) | ☐ |
| D1.11 | The fallback-aligned tool row containing `run_query` on Run B shows failed status on B and a non-failed counterpart on A | ☐ |

### D2. Retrieval Compare

Navigate to compare page: select `rag-tracing-demo-a` as Run A and `rag-tracing-demo-b` as Run B.

| # | Check | Done |
|---|-------|------|
| D2.1 | Retrieval compare section (metadata identity) visible | ☐ |
| D2.2 | Backend diff: `pgvector` → `pinecone` highlighted | ☐ |
| D2.3 | Index diff: `docs-v2` → `docs-v3` highlighted | ☐ |
| D2.4 | Stage: `composite` on both sides (no diff highlight) | ☐ |
| D2.5 | Retrieval output structured diff visible (not raw JSON) | ☐ |
| D2.6 | Candidate count: 50 → 120 highlighted | ☐ |
| D2.7 | Selected count: 5 → 8 highlighted | ☐ |
| D2.8 | Token estimate: 1800 → 3200 highlighted | ☐ |
| D2.9 | Latency: 145 → 230 highlighted | ☐ |
| D2.10 | Query text: same on both sides (no diff highlight) | ☐ |
| D2.11 | Raw/Structured toggle works on retrieval output diff | ☐ |
| D2.12 | Insight block: highest-priority retrieval insight visible — backend divergence or count divergence, according to `computeInsight` priority ordering (only one insight per step pair) | ☐ |
| D2.13 | LLM synthesizer compare works normally | ☐ |
| D2.14 | No identity fields duplicated between metadata section and output section | ☐ |

---

## E. Regression Checks

| # | Check | Done |
|---|-------|------|
| E1 | Run `demo_tool_lifecycle.py` — tool compare still works correctly | ☐ |
| E2 | Generic non-MCP, non-retrieval tool steps render without badges | ☐ |
| E3 | LLM steps render without MCP or retrieval badges | ☐ |
| E4 | No console errors in browser devtools on run-detail or compare | ☐ |
| E5 | No layout breakage when many badges wrap in step headers | ☐ |
| E6 | No crash when comparing a run that has MCP metadata against one that does not | ☐ |
| E7 | Artifact list renders correctly with mixed artifact types (tool + MCP + retrieval) | ☐ |
| E8 | Blob-backed artifacts (if any) load correctly via lazy fetch | ☐ |
| E9 | Compare page: one-sided steps render with "—" and italic styling | ☐ |
| E10 | Compare page: generic DataDiffRow still used for non-retrieval output | ☐ |

---

## F. Signoff

| Area | Reviewer | Date | Status |
|------|----------|------|--------|
| MCP run-detail | | | ☐ Pass / ☐ Fail |
| MCP compare | | | ☐ Pass / ☐ Fail |
| Retrieval run-detail | | | ☐ Pass / ☐ Fail |
| Retrieval compare | | | ☐ Pass / ☐ Fail |
| Regression | | | ☐ Pass / ☐ Fail |
| Overall v1 signoff | | | ☐ Pass / ☐ Fail |

---

## Notes

- Both demos are fully deterministic — no network calls, no real providers
- Demo scripts print a full inspection guide with expected badges, rows, and sections
- Compare outcomes are predictable: exact field values listed in demo output
- If any check fails, note the failure in the signoff table and file a follow-up issue
- This checklist covers the v1 scope defined in `tasks/mcp-skills-rag-implementation-plan.md`
