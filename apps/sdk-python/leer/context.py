from __future__ import annotations

from contextvars import ContextVar

from leer.models import TraceRun, TraceStep

_current_run: ContextVar[TraceRun | None] = ContextVar("_current_run", default=None)
_step_stack: ContextVar[list[TraceStep]] = ContextVar("_step_stack", default=[])
_event_counter: ContextVar[int] = ContextVar("_event_counter", default=0)


def get_current_run() -> TraceRun | None:
    return _current_run.get()


def set_current_run(run: TraceRun | None) -> None:
    _current_run.set(run)


def get_step_stack() -> list[TraceStep]:
    return _step_stack.get()


def push_step(s: TraceStep) -> None:
    stack = _step_stack.get()
    _step_stack.set([*stack, s])


def pop_step() -> TraceStep | None:
    stack = _step_stack.get()
    if not stack:
        return None
    _step_stack.set(stack[:-1])
    return stack[-1]


def current_step() -> TraceStep | None:
    stack = _step_stack.get()
    return stack[-1] if stack else None


def next_event_index() -> int:
    idx = _event_counter.get()
    _event_counter.set(idx + 1)
    return idx


def reset_context() -> None:
    _event_counter.set(0)
    _step_stack.set([])
