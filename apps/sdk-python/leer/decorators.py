from __future__ import annotations

import functools
import traceback
from typing import Any, Callable, TypeVar

from leer.client import submit
from leer.context import (
    get_current_run,
    next_event_index,
    reset_context,
    set_current_run,
)
from leer.models import TraceEvent, TraceRun, _now

F = TypeVar("F", bound=Callable[..., Any])


def _emit(run: TraceRun, event_type: str, step_id: str | None = None, payload: dict[str, Any] | None = None) -> None:
    run.events.append(
        TraceEvent(
            event_type=event_type,
            sequence_index=next_event_index(),
            step_id=step_id,
            payload=payload or {},
        )
    )


def trace(workflow_name: str, metadata: dict[str, Any] | None = None) -> Callable[[F], F]:
    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if get_current_run() is not None:
                return fn(*args, **kwargs)

            run = TraceRun(workflow_name=workflow_name, metadata=metadata or {})
            run.status = "running"
            run.started_at = _now()

            set_current_run(run)
            reset_context()

            _emit(run, "run.created")
            _emit(run, "run.started")

            try:
                result = fn(*args, **kwargs)
            except Exception:
                run.status = "failed"
                run.ended_at = _now()
                run.error_summary = {"traceback": traceback.format_exc()}
                _emit(run, "run.failed")
                submit(run)
                set_current_run(None)
                raise
            else:
                run.status = "completed"
                run.ended_at = _now()
                if result is not None:
                    run.output_summary = {"result_preview": str(result)[:500]}
                _emit(run, "run.completed")
                submit(run)
                set_current_run(None)
                return result

        return wrapper  # type: ignore[return-value]
    return decorator
