from app.models import Run, Step
from app.schemas import CompareRunDiff, CompareStepDiff


def build_step_diffs(steps_a: list[Step], steps_b: list[Step]) -> list[CompareStepDiff]:
    by_index_a: dict[int, Step] = {s.sequence_index: s for s in steps_a}
    by_index_b: dict[int, Step] = {s.sequence_index: s for s in steps_b}

    all_indices = sorted(set(by_index_a) | set(by_index_b))

    diffs: list[CompareStepDiff] = []
    for idx in all_indices:
        a = by_index_a.get(idx)
        b = by_index_b.get(idx)

        diffs.append(CompareStepDiff(
            sequence_index=idx,
            name_a=a.name if a else None,
            name_b=b.name if b else None,
            step_type_a=a.step_type if a else None,
            step_type_b=b.step_type if b else None,
            exists_in_a=a is not None,
            exists_in_b=b is not None,
            status_a=a.status if a else None,
            status_b=b.status if b else None,
            status_diff=_neq(a.status if a else None, b.status if b else None),
            output_summary_a=a.output_summary if a else None,
            output_summary_b=b.output_summary if b else None,
            output_diff=_neq(a.output_summary if a else None, b.output_summary if b else None),
            error_summary_a=a.error_summary if a else None,
            error_summary_b=b.error_summary if b else None,
            error_diff=_neq(a.error_summary if a else None, b.error_summary if b else None),
        ))

    return diffs


def build_run_diff(run_a: Run, run_b: Run) -> CompareRunDiff:
    return CompareRunDiff(
        status_a=run_a.status,
        status_b=run_b.status,
        status_diff=_neq(run_a.status, run_b.status),
        output_summary_a=run_a.output_summary,
        output_summary_b=run_b.output_summary,
        output_diff=_neq(run_a.output_summary, run_b.output_summary),
        error_summary_a=run_a.error_summary,
        error_summary_b=run_b.error_summary,
        error_diff=_neq(run_a.error_summary, run_b.error_summary),
    )


def _neq(a: object, b: object) -> bool:
    return a != b
