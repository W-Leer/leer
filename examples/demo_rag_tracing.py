"""
Demo: RAG tracing — retrieval phases, artifacts, metadata, and compare.

Creates two deterministic runs (A and B) that exercise full retrieval
pipeline tracing.  No real provider, vector DB, or search calls required.

Run A — "rag-tracing-demo-a":
  [tool] vector_search   — retrieval stage: composite (full pipeline)
      capability_kind=retrieval, backend=pgvector, index=docs-v2
      Artifacts: retrieval_request, retrieval_candidates (50),
                 retrieval_rerank, retrieval_selected (5),
                 retrieval_context (text)
      output_summary: kind=retrieval with counts
  [llm] synthesizer      — uses retrieved context to answer

Run B — "rag-tracing-demo-b":
  [tool] vector_search   — retrieval stage: composite (full pipeline)
      capability_kind=retrieval, backend=pinecone, index=docs-v3
      Artifacts: retrieval_request, retrieval_candidates (120),
                 retrieval_rerank, retrieval_selected (8),
                 retrieval_context (text)
      output_summary: kind=retrieval with different counts
  [llm] synthesizer      — uses retrieved context to answer

Compare A vs B should surface:
  - retrieval badge and stage badge on tool steps
  - retrieval compare section: backend pgvector → pinecone
  - retrieval compare section: index docs-v2 → docs-v3
  - retrieval output diff: candidate_count 50 → 120, selected_count 5 → 8
  - retrieval output diff: tokens 1800 → 3200
  - insight: retrieval backend divergence and/or count divergence
  - retrieval artifacts visible in artifact list

Prerequisites:
  - API running at http://127.0.0.1:8000
  - Postgres running with migrations applied

Run (from repo root):
  cd apps/sdk-python && uv run python ../../examples/demo_rag_tracing.py
"""

from __future__ import annotations

import json
from typing import Any

from leer import (
    attach_artifact,
    capability_metadata,
    configure,
    create_retrieval_candidates_artifact,
    create_retrieval_context_artifact,
    create_retrieval_rerank_artifact,
    create_retrieval_request_artifact,
    create_retrieval_selected_artifact,
    retrieval_metadata,
    retrieval_output_summary,
    step,
    tool_step,
    trace,
)
from leer.context import get_current_run

configure(
    api_base_url="http://127.0.0.1:8000",
    project_slug="demo-project",
)


# ---------------------------------------------------------------------------
# Fake document generators
# ---------------------------------------------------------------------------

def _fake_candidates(count: int, prefix: str = "doc") -> list[dict[str, Any]]:
    return [
        {
            "id": f"{prefix}_{i:03d}",
            "text": f"Document {i} content about authentication and user management.",
            "score": round(0.95 - (i * 0.008), 4),
            "metadata": {"source": f"section_{i % 5}", "page": i},
        }
        for i in range(count)
    ]


def _fake_reranked(candidates: list[dict[str, Any]], keep: int) -> list[dict[str, Any]]:
    reranked = []
    for i, doc in enumerate(candidates[:keep * 2]):
        reranked.append({
            **doc,
            "rerank_score": round(0.99 - (i * 0.015), 4),
            "original_rank": i,
        })
    reranked.sort(key=lambda d: d["rerank_score"], reverse=True)
    return reranked[:keep]


def _fake_context(selected: list[dict[str, Any]]) -> str:
    lines = []
    for doc in selected:
        lines.append(f"[{doc['id']}] {doc['text']}")
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Retrieval step builder
# ---------------------------------------------------------------------------

def _retrieval_step_meta(
    *,
    backend: str,
    index: str,
    stage: str = "composite",
) -> dict[str, Any]:
    """Build combined metadata for a retrieval tool step."""
    meta = retrieval_metadata(
        retrieval_stage=stage,
        retrieval_backend=backend,
        index_name=index,
    )
    meta.update(capability_metadata(
        capability_kind="retrieval",
        capability_name="vector_search",
        capability_label="Vector Search",
    ))
    return meta


def _run_retrieval_pipeline(
    *,
    query: str,
    backend: str,
    index: str,
    candidate_count: int,
    selected_count: int,
    token_estimate: int,
    latency_ms: int,
) -> dict[str, Any]:
    """Execute a fake retrieval pipeline as a single tool step with all artifacts."""

    step_meta = _retrieval_step_meta(backend=backend, index=index)

    with tool_step(
        "vector_search",
        metadata=step_meta,
    ) as s:
        s.input = {"query": query, "top_k": candidate_count}

        # Phase 1: Request
        attach_artifact(create_retrieval_request_artifact(
            data={
                "query": query,
                "top_k": candidate_count,
                "filters": {"status": "published"},
                "backend": backend,
                "index": index,
            },
            retrieval_backend=backend,
            index_name=index,
            query_text=query,
            step_id=s.id,
        ))

        # Phase 2: Candidates
        candidates = _fake_candidates(candidate_count)
        attach_artifact(create_retrieval_candidates_artifact(
            data={"documents": candidates, "total_matches": candidate_count * 3},
            candidate_count=candidate_count,
            retrieval_backend=backend,
            index_name=index,
            step_id=s.id,
        ))

        # Phase 3: Rerank
        reranked = _fake_reranked(candidates, selected_count * 2)
        attach_artifact(create_retrieval_rerank_artifact(
            data={"reranked": reranked, "model": "cross-encoder-v2"},
            candidate_count=candidate_count,
            selected_count=len(reranked),
            retrieval_backend=backend,
            step_id=s.id,
        ))

        # Phase 4: Selected
        selected = reranked[:selected_count]
        attach_artifact(create_retrieval_selected_artifact(
            data={"selected": selected},
            selected_count=selected_count,
            retrieval_backend=backend,
            index_name=index,
            step_id=s.id,
        ))

        # Phase 5: Context
        context_text = _fake_context(selected)
        attach_artifact(create_retrieval_context_artifact(
            data=context_text,
            context_token_estimate=token_estimate,
            selected_count=selected_count,
            step_id=s.id,
        ))

        s.output = {"selected_count": selected_count, "context_tokens": token_estimate}
        s.output_summary = retrieval_output_summary(
            retrieval_stage="composite",
            retrieval_backend=backend,
            index_name=index,
            query_text=query[:80],
            candidate_count=candidate_count,
            selected_count=selected_count,
            context_token_estimate=token_estimate,
            latency_ms=latency_ms,
        )

    return {"context": context_text, "selected_count": selected_count}


# ---------------------------------------------------------------------------
# Run A — pgvector / docs-v2 / 50 candidates → 5 selected
# ---------------------------------------------------------------------------

@trace(workflow_name="rag-tracing-demo-a")
def run_a() -> dict[str, Any]:
    run_id = get_current_run().id  # type: ignore[union-attr]

    retrieval = _run_retrieval_pipeline(
        query="How does user authentication work in the system?",
        backend="pgvector",
        index="docs-v2",
        candidate_count=50,
        selected_count=5,
        token_estimate=1800,
        latency_ms=145,
    )

    with step("synthesizer", step_type="llm", metadata={"provider": "fake", "model": "demo-v1"}) as llm:
        llm.metadata["llm"] = {
            "provider": "fake",
            "model": "demo-v1",
            "input": {
                "system": "Answer using the provided context.",
                "messages": [
                    {"role": "user", "content": "How does user authentication work?"},
                    {"role": "system", "content": f"Context ({retrieval['selected_count']} docs):\n{retrieval['context'][:500]}"},
                ],
                "tools": [],
            },
            "output": {
                "text": "Authentication uses JWT tokens with refresh rotation. Users log in via /auth/login which validates credentials against bcrypt hashes.",
                "tool_calls": [],
                "content_blocks": [],
            },
            "usage": {"prompt_tokens": 800, "completion_tokens": 45, "total_tokens": 845},
            "meta": {"latency_ms": 520, "finish_reason": "stop"},
        }
        llm.output_summary = {"text": "Authentication uses JWT tokens with refresh rotation..."}

    return {
        "status": "completed",
        "backend": "pgvector",
        "index": "docs-v2",
        "candidates": 50,
        "selected": 5,
        "context_tokens": 1800,
        "run_id": run_id,
    }


# ---------------------------------------------------------------------------
# Run B — pinecone / docs-v3 / 120 candidates → 8 selected
# ---------------------------------------------------------------------------

@trace(workflow_name="rag-tracing-demo-b")
def run_b() -> dict[str, Any]:
    run_id = get_current_run().id  # type: ignore[union-attr]

    retrieval = _run_retrieval_pipeline(
        query="How does user authentication work in the system?",
        backend="pinecone",
        index="docs-v3",
        candidate_count=120,
        selected_count=8,
        token_estimate=3200,
        latency_ms=230,
    )

    with step("synthesizer", step_type="llm", metadata={"provider": "fake", "model": "demo-v1"}) as llm:
        llm.metadata["llm"] = {
            "provider": "fake",
            "model": "demo-v1",
            "input": {
                "system": "Answer using the provided context.",
                "messages": [
                    {"role": "user", "content": "How does user authentication work?"},
                    {"role": "system", "content": f"Context ({retrieval['selected_count']} docs):\n{retrieval['context'][:500]}"},
                ],
                "tools": [],
            },
            "output": {
                "text": "The system authenticates users through a multi-step flow: credential validation, JWT issuance with short-lived access tokens, and rotating refresh tokens stored in httpOnly cookies.",
                "tool_calls": [],
                "content_blocks": [],
            },
            "usage": {"prompt_tokens": 1400, "completion_tokens": 55, "total_tokens": 1455},
            "meta": {"latency_ms": 680, "finish_reason": "stop"},
        }
        llm.output_summary = {"text": "The system authenticates users through a multi-step flow..."}

    return {
        "status": "completed",
        "backend": "pinecone",
        "index": "docs-v3",
        "candidates": 120,
        "selected": 8,
        "context_tokens": 3200,
        "run_id": run_id,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    sep = "=" * 70

    print(sep)
    print("Demo: RAG Tracing — Retrieval Phases, Artifacts, and Compare")
    print(sep)
    print()

    print("Creating Run A (rag-tracing-demo-a) — pgvector / docs-v2 ...")
    out_a = run_a()
    id_a = out_a.get("run_id", "?")
    print(f"  Run ID: {id_a}")
    print(f"  Result: {json.dumps(out_a)}")
    print()

    print("Creating Run B (rag-tracing-demo-b) — pinecone / docs-v3 ...")
    out_b = run_b()
    id_b = out_b.get("run_id", "?")
    print(f"  Run ID: {id_b}")
    print(f"  Result: {json.dumps(out_b)}")
    print()

    print(sep)
    print("INSPECTION GUIDE")
    print(sep)
    print()

    print(f"Run A — rag-tracing-demo-a  (id: {id_a})")
    print("  Steps: [tool] vector_search → [llm] synthesizer")
    print("  Backend: pgvector, Index: docs-v2")
    print("  Candidates: 50, Selected: 5, Tokens: ~1800")
    print("  Artifacts on vector_search:")
    print("    1. retrieval_request  (query + filters)")
    print("    2. retrieval_candidates (50 documents with scores)")
    print("    3. retrieval_rerank   (cross-encoder-v2 reranked)")
    print("    4. retrieval_selected (5 documents)")
    print("    5. retrieval_context  (plain text, ~1800 tokens)")
    print("    6. tool_request       (auto-generated)")
    print("    7. tool_response      (auto-generated)")
    print()

    print(f"Run B — rag-tracing-demo-b  (id: {id_b})")
    print("  Steps: [tool] vector_search → [llm] synthesizer")
    print("  Backend: pinecone, Index: docs-v3")
    print("  Candidates: 120, Selected: 8, Tokens: ~3200")
    print("  Same artifact structure, different counts and backend")
    print()

    print(f"Quick links:")
    print(f"  Run A detail:  http://localhost:3000/runs/{id_a}")
    print(f"  Run B detail:  http://localhost:3000/runs/{id_b}")
    print(f"  Compare A / B: http://localhost:3000/compare?a={id_a}&b={id_b}")
    print()

    print("RUN-DETAIL CHECKS:")
    print("  - Retrieval badge (teal) on vector_search step")
    print("  - Retrieval stage badge: composite")
    print("  - Capability badge: retrieval")
    print("  - Retrieval metadata rows: backend, index, stage")
    print("  - All 5 retrieval artifacts visible in artifact list")
    print("  - retrieval_context readable as plain text")
    print("  - retrieval_candidates has 50/120 documents (JSON viewer)")
    print("  - tool_request / tool_response also present (auto-generated)")
    print("  - output_summary shows kind=retrieval with counts")
    print()

    print("COMPARE CHECKS (compare Run A vs Run B):")
    print("  - Retrieval compare section (metadata identity):")
    print("      stage: composite = composite (no diff)")
    print("      backend: pgvector → pinecone (changed)")
    print("      index: docs-v2 → docs-v3 (changed)")
    print("  - Retrieval output diff (counts/result):")
    print("      candidates: 50 → 120 (changed)")
    print("      selected: 5 → 8 (changed)")
    print("      tokens: 1800 → 3200 (changed)")
    print("      latency: 145 → 230 (changed)")
    print("      query: same on both sides")
    print("  - Insight: backend divergence or count divergence")
    print("    (one insight per step pair, highest priority wins)")
    print("  - LLM synthesizer: token usage differs (845 → 1455)")
    print()

    print("REGRESSION CHECKS:")
    print("  - Generic tool compare still works for vector_search")
    print("  - LLM step renders normally (no retrieval badges)")
    print("  - No console errors")
    print("  - No layout breakage in compare with many diff fields")
    print()

    print("Open http://localhost:3000 to inspect.")
    print(sep)


if __name__ == "__main__":
    main()
