"""Tests for retrieval / RAG artifact helpers."""

import json

from leer.retrieval_artifacts import (
    create_retrieval_candidates_artifact,
    create_retrieval_context_artifact,
    create_retrieval_rerank_artifact,
    create_retrieval_request_artifact,
    create_retrieval_selected_artifact,
)


# -- retrieval_request -----------------------------------------------------


def test_request_minimal():
    a = create_retrieval_request_artifact({"query": "hello"})
    assert a.artifact_type == "retrieval_request"
    assert a.role == "input"
    assert a.format == "json"
    assert a.storage_kind == "inline"
    assert a.metadata["capability_kind"] == "retrieval"
    assert a.metadata["retrieval_stage"] == "request"


def test_request_full_metadata():
    a = create_retrieval_request_artifact(
        {"query": "auth", "top_k": 10},
        step_id="step_1",
        retrieval_backend="pgvector",
        index_name="docs",
        query_text="auth",
        parent_llm_step_id="llm_1",
    )
    m = a.metadata
    assert m["retrieval_backend"] == "pgvector"
    assert m["index_name"] == "docs"
    assert m["query_text"] == "auth"
    assert m["parent_llm_step_id"] == "llm_1"
    assert a.step_id == "step_1"


def test_request_omits_none():
    a = create_retrieval_request_artifact(
        {"q": 1},
        retrieval_backend=None,
        index_name=None,
    )
    assert "retrieval_backend" not in a.metadata
    assert "index_name" not in a.metadata


# -- retrieval_candidates --------------------------------------------------


def test_candidates_minimal():
    a = create_retrieval_candidates_artifact({"documents": [{"id": 1}]})
    assert a.artifact_type == "retrieval_candidates"
    assert a.role == "output"
    assert a.metadata["retrieval_stage"] == "candidates"
    assert a.metadata["capability_kind"] == "retrieval"


def test_candidates_with_count():
    a = create_retrieval_candidates_artifact(
        {"documents": [{"id": i} for i in range(50)]},
        candidate_count=50,
        retrieval_backend="elasticsearch",
        index_name="articles",
    )
    assert a.metadata["candidate_count"] == 50
    assert a.metadata["retrieval_backend"] == "elasticsearch"
    assert a.metadata["index_name"] == "articles"
    assert "50 candidates" in a.preview_text


def test_candidates_preview_without_count_falls_back_to_json():
    docs = [{"id": i} for i in range(3)]
    a = create_retrieval_candidates_artifact({"documents": docs})
    assert a.preview_text is not None
    assert "candidates" not in a.preview_text


def test_candidates_step_id():
    a = create_retrieval_candidates_artifact({"d": []}, step_id="s_abc")
    assert a.step_id == "s_abc"


# -- retrieval_rerank ------------------------------------------------------


def test_rerank_basic():
    a = create_retrieval_rerank_artifact(
        {"reranked": [{"id": 1, "score": 0.95}]},
        candidate_count=10,
        selected_count=3,
    )
    assert a.artifact_type == "retrieval_rerank"
    assert a.role == "output"
    assert a.metadata["retrieval_stage"] == "rerank"
    assert a.metadata["candidate_count"] == 10
    assert a.metadata["selected_count"] == 3


def test_rerank_metadata_propagation():
    a = create_retrieval_rerank_artifact(
        {"data": []},
        retrieval_backend="cohere",
        parent_llm_step_id="llm_5",
    )
    assert a.metadata["retrieval_backend"] == "cohere"
    assert a.metadata["parent_llm_step_id"] == "llm_5"


# -- retrieval_selected ----------------------------------------------------


def test_selected_basic():
    a = create_retrieval_selected_artifact(
        {"documents": [{"id": 1}, {"id": 2}]},
        selected_count=2,
    )
    assert a.artifact_type == "retrieval_selected"
    assert a.role == "output"
    assert a.metadata["retrieval_stage"] == "selected"
    assert a.metadata["selected_count"] == 2
    assert "2 selected" in a.preview_text


def test_selected_full_metadata():
    a = create_retrieval_selected_artifact(
        {"chunks": ["a", "b"]},
        selected_count=2,
        retrieval_backend="pinecone",
        index_name="kb",
        parent_llm_step_id="llm_x",
        step_id="step_sel",
    )
    assert a.metadata["retrieval_backend"] == "pinecone"
    assert a.metadata["index_name"] == "kb"
    assert a.step_id == "step_sel"


def test_selected_preview_without_count_falls_back_to_json():
    docs = [{"id": i} for i in range(3)]
    a = create_retrieval_selected_artifact({"documents": docs})
    assert a.preview_text is not None
    assert "selected" not in a.preview_text


# -- retrieval_context -----------------------------------------------------


def test_context_json():
    a = create_retrieval_context_artifact(
        {"blocks": ["chunk1", "chunk2"]},
        context_token_estimate=500,
    )
    assert a.artifact_type == "retrieval_context"
    assert a.role == "output"
    assert a.format == "json"
    assert a.metadata["retrieval_stage"] == "context"
    assert a.metadata["context_token_estimate"] == 500


def test_context_text():
    a = create_retrieval_context_artifact(
        "Here is the assembled context for the model...",
        context_token_estimate=200,
    )
    assert a.artifact_type == "retrieval_context"
    assert a.format == "text"
    assert a.mime_type == "text/plain"
    assert a.inline_data == {"text": "Here is the assembled context for the model..."}
    assert a.metadata["retrieval_stage"] == "context"
    assert a.metadata["context_token_estimate"] == 200


def test_context_text_preview():
    text = "A" * 300
    a = create_retrieval_context_artifact(text)
    assert len(a.preview_text) == 200


def test_context_metadata():
    a = create_retrieval_context_artifact(
        {"packed": True},
        selected_count=5,
        parent_llm_step_id="llm_z",
        step_id="step_ctx",
    )
    assert a.metadata["selected_count"] == 5
    assert a.metadata["parent_llm_step_id"] == "llm_z"
    assert a.step_id == "step_ctx"


# -- Cross-cutting ---------------------------------------------------------


def test_all_artifacts_have_capability_kind():
    artifacts = [
        create_retrieval_request_artifact({"q": "x"}),
        create_retrieval_candidates_artifact({"d": []}),
        create_retrieval_rerank_artifact({"r": []}),
        create_retrieval_selected_artifact({"s": []}),
        create_retrieval_context_artifact({"c": []}),
        create_retrieval_context_artifact("text context"),
    ]
    for a in artifacts:
        assert a.metadata["capability_kind"] == "retrieval", (
            f"{a.artifact_type} missing capability_kind"
        )


def test_all_artifacts_have_stage():
    expected = {
        "retrieval_request": "request",
        "retrieval_candidates": "candidates",
        "retrieval_rerank": "rerank",
        "retrieval_selected": "selected",
        "retrieval_context": "context",
    }
    artifacts = [
        create_retrieval_request_artifact({"q": "x"}),
        create_retrieval_candidates_artifact({"d": []}),
        create_retrieval_rerank_artifact({"r": []}),
        create_retrieval_selected_artifact({"s": []}),
        create_retrieval_context_artifact({"c": []}),
    ]
    for a in artifacts:
        assert a.metadata["retrieval_stage"] == expected[a.artifact_type]


def test_all_artifacts_json_safe():
    artifacts = [
        create_retrieval_request_artifact({"q": "x"}, retrieval_backend="pg"),
        create_retrieval_candidates_artifact({"d": [1, 2]}, candidate_count=2),
        create_retrieval_rerank_artifact({"r": [3]}, selected_count=1),
        create_retrieval_selected_artifact({"s": [4]}, selected_count=1),
        create_retrieval_context_artifact({"c": "block"}, context_token_estimate=99),
        create_retrieval_context_artifact("plain text"),
    ]
    for a in artifacts:
        json.dumps(a.inline_data)
        json.dumps(a.metadata)


def test_no_caller_mutation():
    data = {"query": "test", "top_k": 5}
    original = dict(data)
    create_retrieval_request_artifact(data, retrieval_backend="pg")
    assert data == original


def test_independent_instances():
    a = create_retrieval_request_artifact({"a": 1}, index_name="idx_a")
    b = create_retrieval_request_artifact({"b": 2}, index_name="idx_b")
    assert a.metadata["index_name"] == "idx_a"
    assert b.metadata["index_name"] == "idx_b"
    a.metadata["injected"] = True
    assert "injected" not in b.metadata


def test_metadata_delegates_to_step1_helper():
    """Metadata must always include capability_kind and retrieval_stage,
    matching the Step 1 retrieval_metadata() canonical shape."""
    a = create_retrieval_request_artifact({"q": "x"})
    assert a.metadata["capability_kind"] == "retrieval"
    assert a.metadata["retrieval_stage"] == "request"

    b = create_retrieval_candidates_artifact({"d": []}, candidate_count=5)
    assert b.metadata["capability_kind"] == "retrieval"
    assert b.metadata["retrieval_stage"] == "candidates"
    assert b.metadata["candidate_count"] == 5


def test_import_from_package():
    from leer import (
        create_retrieval_candidates_artifact,
        create_retrieval_context_artifact,
        create_retrieval_rerank_artifact,
        create_retrieval_request_artifact,
        create_retrieval_selected_artifact,
    )
    assert callable(create_retrieval_request_artifact)
    assert callable(create_retrieval_candidates_artifact)
    assert callable(create_retrieval_rerank_artifact)
    assert callable(create_retrieval_selected_artifact)
    assert callable(create_retrieval_context_artifact)
