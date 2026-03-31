"""
Run comparison service.

Matching strategy (deterministic, no embeddings):

  Phase 1 — Exact name match (strongest signal)
    Steps sharing the same ``name`` are paired first.
    Duplicate names are resolved by nearest ``sequence_index``.

  Phase 2 — Fallback: same step_type + nearest unmatched sequence_index
    Only considered for remaining unmatched steps.
    Does not force a match when step types differ.
    Rejects candidates beyond ``_MAX_FALLBACK_DISTANCE`` to avoid
    matching structurally unrelated steps that happen to share a type.

  Phase 3 — Remaining unmatched → missing
    Truthful missing rows; never silently dropped.

Results ordered by the earliest available sequence_index across A / B.
"""

from __future__ import annotations

from typing import Any

from app.models import Run, Step
from app.schemas import CompareRunDiff, CompareStepDiff


# ===================================================================
# Public API
# ===================================================================

def build_run_diff(run_a: Run, run_b: Run) -> CompareRunDiff:
    return CompareRunDiff(
        status_a=run_a.status,
        status_b=run_b.status,
        status_diff=run_a.status != run_b.status,
        output_summary_a=run_a.output_summary,
        output_summary_b=run_b.output_summary,
        output_diff=run_a.output_summary != run_b.output_summary,
        error_summary_a=run_a.error_summary,
        error_summary_b=run_b.error_summary,
        error_diff=run_a.error_summary != run_b.error_summary,
    )


def build_step_diffs(
    steps_a: list[Step],
    steps_b: list[Step],
) -> list[CompareStepDiff]:
    """Match steps across two runs and return a sorted list of compare rows."""
    pairs = _match_steps(steps_a, steps_b)
    diffs = [_build_row(sa, sb, kind) for sa, sb, kind in pairs]
    diffs.sort(key=_sort_key)
    return diffs


# ===================================================================
# Three-phase matching
# ===================================================================

_Pair = tuple[Step | None, Step | None, str]

# Fallback matches beyond this sequence_index distance are rejected.
# Keeps matching truthful when runs have very different structures.
_MAX_FALLBACK_DISTANCE = 3


def _match_steps(
    steps_a: list[Step],
    steps_b: list[Step],
) -> list[_Pair]:
    matched_a: set[int] = set()          # id(step) of consumed A steps
    matched_b: set[int] = set()          # id(step) of consumed B steps
    result: list[_Pair] = []

    # Phase 1: exact name match
    _phase_exact_name(steps_a, steps_b, matched_a, matched_b, result)

    # Phase 2: fallback — same step_type, nearest sequence_index
    _phase_fallback_type_index(steps_a, steps_b, matched_a, matched_b, result)

    # Phase 3: unmatched → missing
    for s in steps_a:
        if id(s) not in matched_a:
            result.append((s, None, "missing"))
    for s in steps_b:
        if id(s) not in matched_b:
            result.append((None, s, "missing"))

    return result


def _phase_exact_name(
    steps_a: list[Step],
    steps_b: list[Step],
    matched_a: set[int],
    matched_b: set[int],
    result: list[_Pair],
) -> None:
    by_name_a: dict[str, list[Step]] = {}
    for s in steps_a:
        by_name_a.setdefault(s.name, []).append(s)

    by_name_b: dict[str, list[Step]] = {}
    for s in steps_b:
        by_name_b.setdefault(s.name, []).append(s)

    for name in by_name_a:
        if name not in by_name_b:
            continue

        pool_a = sorted(
            [s for s in by_name_a[name] if id(s) not in matched_a],
            key=lambda s: s.sequence_index,
        )
        pool_b = sorted(
            [s for s in by_name_b[name] if id(s) not in matched_b],
            key=lambda s: s.sequence_index,
        )

        for sa, sb in zip(pool_a, pool_b):
            result.append((sa, sb, "exact_name"))
            matched_a.add(id(sa))
            matched_b.add(id(sb))


def _phase_fallback_type_index(
    steps_a: list[Step],
    steps_b: list[Step],
    matched_a: set[int],
    matched_b: set[int],
    result: list[_Pair],
) -> None:
    remaining_a = sorted(
        [s for s in steps_a if id(s) not in matched_a],
        key=lambda s: s.sequence_index,
    )

    for sa in remaining_a:
        best: Step | None = None
        best_dist = float("inf")

        for sb in steps_b:
            if id(sb) in matched_b:
                continue
            if sb.step_type != sa.step_type:
                continue
            dist = abs(sa.sequence_index - sb.sequence_index)
            if dist < best_dist or (
                dist == best_dist
                and best is not None
                and sb.sequence_index < best.sequence_index
            ):
                best_dist = dist
                best = sb

        if best is not None and best_dist <= _MAX_FALLBACK_DISTANCE:
            result.append((sa, best, "fallback_type_index"))
            matched_a.add(id(sa))
            matched_b.add(id(best))


# ===================================================================
# Per-row construction
# ===================================================================

def _extract_llm(step: Step | None) -> dict[str, Any] | None:
    """Surface the already-normalized llm payload stored in step metadata."""
    if step is None:
        return None
    meta = step.metadata_
    if isinstance(meta, dict):
        return meta.get("llm")
    return None


def _attr(step: Step | None, name: str) -> Any:
    return getattr(step, name, None) if step else None


def _build_row(sa: Step | None, sb: Step | None, kind: str) -> CompareStepDiff:
    return CompareStepDiff(
        match_kind=kind,
        exists_in_a=sa is not None,
        exists_in_b=sb is not None,

        sequence_index_a=_attr(sa, "sequence_index"),
        sequence_index_b=_attr(sb, "sequence_index"),

        parent_step_id_a=_attr(sa, "parent_step_id"),
        parent_step_id_b=_attr(sb, "parent_step_id"),

        name_a=_attr(sa, "name"),
        name_b=_attr(sb, "name"),
        step_type_a=_attr(sa, "step_type"),
        step_type_b=_attr(sb, "step_type"),

        status_a=_attr(sa, "status"),
        status_b=_attr(sb, "status"),
        status_diff=_attr(sa, "status") != _attr(sb, "status"),

        input_summary_a=_attr(sa, "input_summary"),
        input_summary_b=_attr(sb, "input_summary"),
        input_diff=_attr(sa, "input_summary") != _attr(sb, "input_summary"),

        output_summary_a=_attr(sa, "output_summary"),
        output_summary_b=_attr(sb, "output_summary"),
        output_diff=_attr(sa, "output_summary") != _attr(sb, "output_summary"),

        error_summary_a=_attr(sa, "error_summary"),
        error_summary_b=_attr(sb, "error_summary"),
        error_diff=_attr(sa, "error_summary") != _attr(sb, "error_summary"),

        duration_ms_a=_attr(sa, "duration_ms"),
        duration_ms_b=_attr(sb, "duration_ms"),

        model_provider_a=_attr(sa, "model_provider"),
        model_provider_b=_attr(sb, "model_provider"),

        model_name_a=_attr(sa, "model_name"),
        model_name_b=_attr(sb, "model_name"),

        # Temporary: full metadata blob. Frontend reads only tool_call_id,
        # provider, model. Extract explicit compare fields when this grows.
        metadata_a=_attr(sa, "metadata_") if sa else None,
        metadata_b=_attr(sb, "metadata_") if sb else None,

        llm_a=_extract_llm(sa),
        llm_b=_extract_llm(sb),
    )


def _sort_key(d: CompareStepDiff) -> tuple[int, int]:
    """Order by earliest available sequence_index, tie-break on A-side."""
    a = d.sequence_index_a if d.sequence_index_a is not None else 999_999
    b = d.sequence_index_b if d.sequence_index_b is not None else 999_999
    return (min(a, b), a)
