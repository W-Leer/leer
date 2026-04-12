"""
Demo: Multimodal artifact rendering end-to-end.

Creates one run with three steps that produce different media artifact types
so you can visually verify multimodal rendering in the Leer UI.

Steps produced:
  Step 0  "generate_image"      → output_image artifact (PNG, ~100 bytes)
  Step 1  "generate_report"     → output_document artifact (PDF, ~1 KB)
  Step 2  "export_data"         → generic binary artifact (CSV, ~200 bytes)
  Step 3  "llm_with_media"      → LLM-style step with content_blocks referencing media

Each step uses small deterministic embedded fixtures — no real provider calls.

Prerequisites:
  - API running at http://127.0.0.1:8000
  - Postgres running with migrations applied

Run (from repo root):
  cd apps/sdk-python && uv run python ../../examples/demo_multimodal.py
"""

from __future__ import annotations

import base64
import struct
import zlib

from leer import configure, step, trace
from leer.artifacts import attach_artifact, create_binary_artifact, create_json_artifact

configure(
    api_base_url="http://127.0.0.1:8000",
    project_slug="demo-project",
)


# ---------------------------------------------------------------------------
# Deterministic fixtures — small base64 payloads
# ---------------------------------------------------------------------------

def _make_png(width: int = 200, height: int = 120) -> bytes:
    """Generate a valid RGB PNG with a simple gradient pattern."""
    raw_rows = bytearray()
    for y in range(height):
        raw_rows.append(0)  # filter byte: None
        for x in range(width):
            r = int(255 * x / width)
            g = int(100 * y / height)
            b = int(200 * (1 - x / width))
            raw_rows.extend((r, g, b))
    compressed = zlib.compress(bytes(raw_rows))

    def _chunk(tag: bytes, data: bytes) -> bytes:
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr_data)
        + _chunk(b"IDAT", compressed)
        + _chunk(b"IEND", b"")
    )

_PNG_BYTES = _make_png()

# Minimal valid PDF (a single blank page)
_PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"xref\n0 4\n"
    b"0000000000 65535 f \n"
    b"0000000009 00000 n \n"
    b"0000000058 00000 n \n"
    b"0000000115 00000 n \n"
    b"trailer<</Size 4/Root 1 0 R>>\n"
    b"startxref\n190\n%%EOF\n"
)

# Small CSV payload
_CSV_BYTES = (
    b"id,name,value,category\n"
    b"1,Alpha,42.5,A\n"
    b"2,Beta,17.3,B\n"
    b"3,Gamma,99.1,A\n"
    b"4,Delta,8.7,C\n"
    b"5,Epsilon,63.2,B\n"
)


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------


@trace(workflow_name="multimodal-demo")
def run_multimodal_demo() -> dict:
    image_art = None
    doc_art = None

    # Step 0: image artifact
    with step("generate_image", step_type="code") as s:
        s.input = {"prompt": "A 200x120 gradient for testing"}
        s.output = {"status": "generated", "format": "png", "dimensions": "200x120"}
        image_art = attach_artifact(create_binary_artifact(
            artifact_type="output_image",
            data=_PNG_BYTES,
            mime_type="image/png",
            role="output",
            filename="demo-image.png",
            preview_text="200x120 gradient test image",
        ))

    # Step 1: PDF document artifact
    with step("generate_report", step_type="code") as s:
        s.input = {"report_type": "quarterly", "format": "pdf"}
        s.output = {"status": "generated", "pages": 1, "size_bytes": len(_PDF_BYTES)}
        doc_art = attach_artifact(create_binary_artifact(
            artifact_type="output_document",
            data=_PDF_BYTES,
            mime_type="application/pdf",
            role="output",
            filename="quarterly-report.pdf",
            preview_text="Single-page blank PDF for testing",
        ))

    # Step 2: generic binary artifact (CSV)
    with step("export_data", step_type="code") as s:
        s.input = {"table": "metrics", "format": "csv"}
        s.output = {"status": "exported", "rows": 5, "size_bytes": len(_CSV_BYTES)}
        attach_artifact(create_binary_artifact(
            artifact_type="data_export",
            data=_CSV_BYTES,
            mime_type="text/csv",
            role="output",
            filename="metrics-export-2026-04-05.csv",
            preview_text="5 rows: Alpha, Beta, Gamma, Delta, Epsilon",
        ))

    # Step 3: LLM-style step with content_blocks that reference media
    # Artifacts must be created inside this step's context so the frontend
    # can match artifact_id in content_blocks to the step's own artifacts.
    with step("llm_with_media", step_type="llm") as s:
        llm_img = attach_artifact(create_binary_artifact(
            artifact_type="output_image",
            data=_PNG_BYTES,
            mime_type="image/png",
            role="output",
            filename="llm-output-image.png",
            preview_text="LLM-generated gradient image",
        ))
        llm_doc = attach_artifact(create_binary_artifact(
            artifact_type="output_document",
            data=_PDF_BYTES,
            mime_type="application/pdf",
            role="output",
            filename="llm-output-report.pdf",
            preview_text="LLM-generated report",
        ))

        s.input = {"prompt": "Generate an image and a report"}
        s.output = {"text": "Here is the generated image and report."}
        s.metadata = {
            "llm": {
                "provider": "demo",
                "model": "multimodal-demo-v1",
                "input": {
                    "system": "You are a multimodal demo assistant.",
                    "messages": [
                        {"role": "user", "content": [
                            {"type": "text", "text": "Generate an image and a report"},
                            {"type": "image_url", "image_url": {"url": "data:image/png;base64,demo"}},
                        ]},
                    ],
                    "tools": [],
                },
                "output": {
                    "text": "Here is the generated image and report.",
                    "tool_calls": [],
                    "content_blocks": [
                        {"type": "text", "text": "Here is the generated image and report."},
                        {
                            "type": "image",
                            "mime_type": "image/png",
                            "artifact_id": llm_img.id,
                            "filename": "llm-output-image.png",
                            "source": {"kind": "artifact", "value": llm_img.id},
                            "preview_text": "LLM-generated gradient image",
                        },
                        {
                            "type": "document",
                            "mime_type": "application/pdf",
                            "artifact_id": llm_doc.id,
                            "filename": "llm-output-report.pdf",
                            "source": {"kind": "artifact", "value": llm_doc.id},
                            "preview_text": "LLM-generated report",
                        },
                    ],
                },
                "usage": {
                    "prompt_tokens": 50,
                    "completion_tokens": 20,
                    "total_tokens": 70,
                },
                "meta": {
                    "finish_reason": "stop",
                    "request_id": None,
                    "latency_ms": 1200,
                },
            },
        }
        s.output_summary = {"text": "Here is the generated image and report."}

    return {"status": "completed", "artifacts_created": 5}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 60)
    print("Demo: Multimodal Artifact Rendering")
    print("=" * 60)
    print()
    print("  Fixtures:")
    print(f"    PNG image:   {len(_PNG_BYTES):>6} bytes  (200x120 gradient)")
    print(f"    PDF doc:     {len(_PDF_BYTES):>6} bytes  (single blank page)")
    print(f"    CSV data:    {len(_CSV_BYTES):>6} bytes  (5 rows)")
    print()
    print("  Creating multimodal demo run...")

    try:
        result = run_multimodal_demo()
        print(f"  Done. Result: {result}")
    except Exception as e:
        print(f"  Failed: {e}")
        return

    print()
    print("=" * 60)
    print("What to inspect in the UI:")
    print("=" * 60)
    print()
    print("  Open http://localhost:3000 → demo-project → multimodal-demo")
    print()
    print("  Step 0: generate_image")
    print("    → Artifacts section should show an IMG badge")
    print("    → Image preview should render (200x120 gradient)")
    print("    → 'blob' badge should appear")
    print()
    print("  Step 1: generate_report")
    print("    → Artifacts section should show a PDF badge")
    print("    → 'Open' button should open the PDF in a new tab")
    print("    → 'Preview' button should toggle inline PDF viewer")
    print("    → Fallback text should appear if browser blocks PDF embed")
    print()
    print("  Step 2: export_data")
    print("    → Artifacts section should show a generic CSV card")
    print("    → MIME type shown as 'text/csv'")
    print("    → 'Open' button should open raw content")
    print("    → Preview text should show '5 rows: Alpha, Beta...'")
    print()
    print("  Step 3: llm_with_media")
    print("    → LLM step detail should show:")
    print("      - Input section with [image] media marker badge")
    print("      - Output text: 'Here is the generated image and report.'")
    print("      - Output media: image content block linked to the PNG artifact")
    print("      - Output media: document content block linked to the PDF artifact")
    print("    → Content block rows should render the image inline")
    print("    → Content block rows should render the PDF card")
    print()
    print("  Compare page:")
    print("    → Run this demo twice to get two runs")
    print("    → Compare should show media badges, not crash")
    print("    → One-sided compare (multimodal vs non-multimodal) should be clean")
    print()
    print("  Edge cases to verify:")
    print("    → Long filename truncation (check CSS)")
    print("    → Multiple media blocks in single output render stacked")
    print("    → Missing artifact_id in content block shows fallback card")
    print("    → No console errors in browser dev tools")


if __name__ == "__main__":
    main()
