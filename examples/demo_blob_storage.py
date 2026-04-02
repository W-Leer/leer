"""
Demo: Blob storage end-to-end validation.

Creates one run containing both inline and blob-backed artifacts so you
can verify the hybrid storage model works correctly in the UI.

Artifacts produced:
  Step 0  "prepare_config"    → small inline artifact (~200 bytes)
  Step 1  "process_events"    → large blob-backed artifact (~350 KB)
  Step 2  "aggregate_results" → large blob-backed artifact (~400 KB)

The API server decides which artifacts stay inline vs offload to blob
storage based on blob_inline_threshold_bytes (default 256 KB).

Prerequisites:
  - API running at http://127.0.0.1:8000
  - Postgres running with migrations applied

Run (from repo root):
  cd apps/sdk-python && uv run python ../../examples/demo_blob_storage.py
"""

from __future__ import annotations

import json

from leer import configure, step, trace
from leer.artifacts import attach_artifact, create_json_artifact

configure(
    api_base_url="http://127.0.0.1:8000",
    project_slug="demo-project",
)


# ---------------------------------------------------------------------------
# Payload generators — realistic JSON that crosses the 256 KB threshold
# ---------------------------------------------------------------------------


def _small_config_payload() -> dict:
    """~200 bytes — stays inline."""
    return {
        "version": "1.2.0",
        "environment": "staging",
        "features": {"blob_storage": True, "streaming": True},
        "limits": {"max_events": 10000, "timeout_ms": 30000},
    }


def _large_events_payload(count: int = 800) -> dict:
    """~350 KB of structured event data — offloads to blob storage."""
    events = []
    for i in range(count):
        events.append({
            "index": i,
            "type": "content_block_delta" if i % 5 != 0 else "message_delta",
            "timestamp_offset_ms": i * 23,
            "delta": {
                "text": f"Token {i}: The quick brown fox jumps over the lazy dog. "
                        f"Sentence number {i} provides additional context for the model output. "
                        f"This ensures the payload is realistically sized for blob threshold testing.",
            },
            "metadata": {
                "chunk_id": f"chunk-{i:04d}",
                "provider": "openai",
                "model": "gpt-4.1",
                "sequence": i,
            },
        })
    return {"events": events, "total_chunks": count, "provider": "openai"}


def _large_results_payload(count: int = 500) -> dict:
    """~400 KB of structured search/analysis results — offloads to blob storage."""
    results = []
    for i in range(count):
        results.append({
            "id": f"result-{i:04d}",
            "title": f"Document {i}: Analysis of distributed tracing patterns in production systems",
            "score": round(0.99 - (i * 0.001), 4),
            "section": ["overview", "architecture", "deployment", "monitoring"][i % 4],
            "snippet": (
                f"Result {i} demonstrates how distributed tracing captures causal relationships "
                f"between service calls. The instrumentation layer records timing, metadata, and "
                f"error states across the full request lifecycle. This entry provides enough text "
                f"to make each result object realistically sized for threshold testing."
            ),
            "metadata": {
                "source": f"docs/section-{i % 20:02d}.md",
                "last_updated": "2026-03-20T10:00:00Z",
                "author": "engineering",
                "tags": ["tracing", "observability", "production"],
            },
        })
    return {
        "results": results,
        "total_matches": count,
        "query_time_ms": 142,
        "meta": {
            "index": "production-v3",
            "shards": 5,
            "max_score": 0.99,
        },
    }


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------


@trace(workflow_name="blob-storage-demo")
def run_blob_demo() -> dict:

    # Step 0: small config artifact — stays inline
    with step("prepare_config", step_type="code") as s:
        config = _small_config_payload()
        s.input = {"source": "environment"}
        s.output = config
        attach_artifact(create_json_artifact(
            artifact_type="config",
            role="output",
            data=config,
            preview_text="staging config — blob_storage=true, streaming=true",
        ))

    # Step 1: large event stream artifact — offloads to blob
    with step("process_events", step_type="code") as s:
        events_payload = _large_events_payload(count=800)
        s.input = {"provider": "openai", "model": "gpt-4.1"}
        s.output = {"status": "processed", "chunk_count": events_payload["total_chunks"]}
        attach_artifact(create_json_artifact(
            artifact_type="event_stream",
            role="output",
            data=events_payload,
            preview_text=f"{events_payload['total_chunks']} chunks from openai/gpt-4.1",
        ))

    # Step 2: large search results artifact — offloads to blob
    with step("aggregate_results", step_type="code") as s:
        results_payload = _large_results_payload(count=500)
        s.input = {"query": "distributed tracing patterns", "index": "production-v3"}
        s.output = {"total_matches": results_payload["total_matches"], "query_time_ms": 142}
        attach_artifact(create_json_artifact(
            artifact_type="search_results",
            role="output",
            data=results_payload,
            preview_text=f"{results_payload['total_matches']} results in 142ms",
        ))

    return {"status": "completed", "artifacts_created": 3}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    # Pre-compute sizes for the summary
    small = json.dumps(_small_config_payload(), separators=(",", ":")).encode()
    large_events = json.dumps(_large_events_payload(800), separators=(",", ":")).encode()
    large_results = json.dumps(_large_results_payload(500), separators=(",", ":")).encode()

    print("=" * 60)
    print("Demo: Blob Storage End-to-End")
    print("=" * 60)
    print()
    print(f"  Payload sizes (compact JSON):")
    print(f"    config artifact:  {len(small):>8,} bytes  → inline")
    print(f"    events artifact:  {len(large_events):>8,} bytes  → blob")
    print(f"    results artifact: {len(large_results):>8,} bytes  → blob")
    print(f"    threshold:        {256 * 1024:>8,} bytes")
    print()

    print("  Creating blob storage demo run...")
    try:
        result = run_blob_demo()
        print(f"  Done. Result: {json.dumps(result)}")
    except Exception as e:
        print(f"  Failed: {e}")
        return

    print()
    print("=" * 60)
    print("What to inspect in the UI:")
    print("=" * 60)
    print()
    print("  Open http://localhost:3000 → demo-project → blob-storage-demo")
    print()
    print("  Step 0: prepare_config")
    print("    → Expand Artifacts → config artifact should be inline")
    print("    → Data renders immediately via StructuredValue")
    print()
    print("  Step 1: process_events")
    print("    → Expand Artifacts → event_stream should show 'blob' badge")
    print("    → Click 'Load artifact' to fetch from blob storage")
    print("    → Verify structured rendering of 800 event objects")
    print()
    print("  Step 2: aggregate_results")
    print("    → Expand Artifacts → search_results should show 'blob' badge")
    print("    → Click 'Load artifact' to fetch from blob storage")
    print("    → Verify structured rendering of 500 result objects")
    print()
    print("  Also check:")
    print("    → Timeline refs show storage_kind / size_bytes for each artifact")
    print("    → Raw toggle works for loaded blob artifacts")
    print("    → Copy button works after loading")


if __name__ == "__main__":
    main()
