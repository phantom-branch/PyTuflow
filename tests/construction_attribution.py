"""Opt-in developer wall-time attribution; no parser mutation or benchmark acceptance.

Exclusive means relative to the registered Python boundaries, NOT all functions.
Unregistered Python work, native calls, blocking I/O and observer overhead belong
inside the nearest active boundary. Generator suspension is outside that span.
"""

from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from inspect import CO_ASYNC_GENERATOR, CO_COROUTINE, CO_GENERATOR, isawaitable
import sys
from time import perf_counter_ns
from types import CodeType, FrameType


@dataclass(frozen=True)
class Target:
    operation: str
    owner_argument: str | None = None


@dataclass
class _Span:
    frame_id: int
    key: tuple[str, str]
    started: int


class Attribution:
    """Single-use, calling-thread observer of explicitly registered code objects.

    Exact control-file classes map to anonymous kinds. An unknown owner boundary
    resets the kind to UNATTRIBUTED rather than charging its work to its parent.
    Neither parser properties nor extension hooks are called to classify owners.
    """

    def __init__(
        self, targets: Iterable[tuple[CodeType, Target]], owner_types: dict[type, str],
        *, clock: Callable[[], int] = perf_counter_ns,
    ) -> None:
        self._targets = {id(code): (code, target) for code, target in targets}
        self._owners = {id(cls): (cls, label) for cls, label in owner_types.items()}
        self.clock = clock
        self._stack: list[_Span] = []
        self._exclusive: dict[tuple[str, str], int] = defaultdict(int)
        self._inclusive: dict[tuple[str, str], int] = defaultdict(int)
        self._entries: dict[tuple[str, str], int] = defaultdict(int)
        self._generator_segments: dict[tuple[str, str], int] = defaultdict(int)
        self._hook = self._observe  # Retain bound-method identity for safe cleanup.
        self._used = False
        self._active = False
        self._started = self._last = self._ended = 0
        self.completed = False
        self.error_type: str | None = None
        self.diagnostic_error: str | None = None

    def _charge(self, now: int) -> None:
        key = self._stack[-1].key if self._stack else ('unattributed', 'UNATTRIBUTED')
        self._exclusive[key] += now - self._last
        self._last = now

    def _observe(self, frame: FrameType, event: str, arg: object) -> None:
        if event not in ('call', 'return') or self.diagnostic_error is not None:
            return
        registered = self._targets.get(id(frame.f_code))
        if registered is None or registered[0] is not frame.f_code:
            return
        target = registered[1]
        now = self.clock()
        self._charge(now)
        if event == 'call':
            owner = self._stack[-1].key[1] if self._stack else 'UNATTRIBUTED'
            if target.owner_argument is not None:
                owner = 'UNATTRIBUTED'
                value = frame.f_locals.get(target.owner_argument)
                known_owner = self._owners.get(id(type(value)))
                if known_owner is not None and known_owner[0] is type(value):
                    owner = known_owner[1]
            key = (target.operation, owner)
            self._entries[key] += 1
            if frame.f_code.co_flags & (CO_GENERATOR | CO_COROUTINE | CO_ASYNC_GENERATOR):
                self._generator_segments[key] += 1
            self._stack.append(_Span(id(frame), key, now))
        elif not self._stack or self._stack[-1].frame_id != id(frame):
            # Do not throw from the hook and alter the observed parser failure.
            self.diagnostic_error = 'Unbalanced registered call/return events'
        else:
            span = self._stack.pop()
            self._inclusive[span.key] += now - span.started

    def run[T](self, action: Callable[[], T]) -> T:
        """Observe a synchronous, fully consumed action and preserve its exception."""
        if self._used:
            raise RuntimeError('Create a fresh Attribution for each invocation')
        if sys.getprofile() is not None:
            raise RuntimeError('An existing profile hook must not be replaced')
        monitoring = getattr(sys, 'monitoring', None)
        if monitoring is not None and monitoring.get_tool(monitoring.PROFILER_ID) is not None:
            raise RuntimeError('The monitoring profiler slot is already owned')
        self._used = self._active = True
        self._started = self._last = self.clock()
        error: BaseException | None = None
        try:
            sys.setprofile(self._hook)
            result = action()
            if isinstance(result, Iterator) or isawaitable(result):
                raise TypeError('Consume lazy work inside the observed action')
            self.completed = True
            return result
        except BaseException as exc:
            error = exc
            self.error_type = type(exc).__name__
            raise
        finally:
            try:
                if sys.getprofile() is self._hook:
                    sys.setprofile(None)
                else:
                    self.diagnostic_error = 'The workload replaced or disabled the profile hook'
                self._ended = self.clock()
                self._charge(self._ended)
                if self._stack:
                    self.diagnostic_error = self.diagnostic_error or 'Capture ended with active spans'
                self._stack.clear()  # Never retain frames or model objects.
                self._active = False
                if self.diagnostic_error is not None:
                    self.completed = False
                    if error is None:
                        raise RuntimeError(self.diagnostic_error)
            except BaseException as capture_error:
                self.completed = False
                self._active = False
                if error is None:
                    raise
                error.add_note(f'Attribution finalisation also failed: {type(capture_error).__name__}')

    def snapshot(self) -> dict[str, object]:
        """Return independent aggregate data, including incomplete captures."""
        if not self._used or self._active:
            raise RuntimeError('A finished capture is required')
        keys = sorted(set(self._exclusive) | set(self._entries))
        return {
            'schema_version': 1,
            'completed': self.completed,
            'error_type': self.error_type,
            'diagnostic_error': self.diagnostic_error,
            'accepted_for_benchmark': False,
            'wall_elapsed_ns': self._ended - self._started,
            'thread_scope': 'calling thread only',
            'timing_basis': 'wall time; nearest registered boundary; observer overhead included',
            'inclusive_warning': 'Nested inclusive spans overlap; never sum them as exclusive costs',
            'count_basis': 'activation segments; generator resumes are not new constructor calls',
            'cells': [
                {
                    'operation': op, 'control_file_kind': owner,
                    'exclusive_ns': self._exclusive[(op, owner)],
                    'inclusive_span_ns': self._inclusive[(op, owner)],
                    'activation_segments': self._entries[(op, owner)],
                    'generator_activation_segments': self._generator_segments[(op, owner)],
                }
                for op, owner in keys
            ],
        }
