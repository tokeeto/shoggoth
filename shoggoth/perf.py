"""Lightweight opt-in timing instrumentation for the render pipeline.

Disabled by default (a single boolean check per `span()` call, no timing
or bookkeeping overhead). Enable it with either:

    from shoggoth.perf import perf
    perf.enabled = True

or by setting the SHOGGOTH_PERF=1 environment variable before the process
starts. Call `perf.reset()` before the flow you want to isolate (e.g. a
single get_card_textures call, to separate a cold render from a warm one)
and `perf.report()` afterwards to print a breakdown sorted by total time.

Each `span(description)` call tags itself with the file:line of whichever
line called it (or of a function passed via `at=`, when the call site
itself isn't distinctive — e.g. all iterations of a loop over a list of
functions), so labels can't drift out of sync as the code is refactored.
"""
import os
import sys
import time
from collections import defaultdict


class _Span:
    __slots__ = ('_tracker', '_label', '_t0')

    def __init__(self, tracker, label):
        self._tracker = tracker
        self._label = label

    def __enter__(self):
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._tracker._record(self._label, time.perf_counter() - self._t0)
        return False


class _NullSpan:
    __slots__ = ()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


_NULL_SPAN = _NullSpan()


class PerfTracker:
    def __init__(self):
        self.enabled = os.environ.get('SHOGGOTH_PERF') == '1'
        self._stats = defaultdict(lambda: [0, 0.0])  # label -> [count, total_seconds]

    def reset(self):
        """Clear accumulated timings. Call before the flow you want isolated."""
        self._stats = defaultdict(lambda: [0, 0.0])

    def span(self, description, at=None):
        """Time a block of code. Use as `with perf.span("description"):`.

        By default the label is tagged with the file:line of the caller.
        Pass `at=some_function` to tag with that function's own definition
        site instead (useful when the call site is shared, e.g. a loop
        dispatching to several different functions).
        """
        if not self.enabled:
            return _NULL_SPAN
        if at is not None:
            code = at.__code__
            filename, lineno = code.co_filename, code.co_firstlineno
        else:
            frame = sys._getframe(1)
            filename, lineno = frame.f_code.co_filename, frame.f_lineno
        label = f'{description} ({os.path.basename(filename)}:{lineno})'
        return _Span(self, label)

    def _record(self, label, elapsed):
        entry = self._stats[label]
        entry[0] += 1
        entry[1] += elapsed

    def report(self, title=None) -> str:
        """Return a report of every span, sorted by total time descending."""
        rows = sorted(self._stats.items(), key=lambda kv: -kv[1][1])
        lines = [title] if title else []
        for label, (count, total) in rows:
            avg = total / count
            lines.append(f'{label} | calls {count} | total {total:.4f}s | avg {avg:.5f}s')
        return '\n'.join(lines)


perf = PerfTracker()
