"""The baseline -- and it is not a straw man.

This is a faithful copy of saknussemm's ``_compute_geometry``
(``formats/alto/rewriter.py:110``), the function that ships today and draws
every box on the rewriter's slow path. It is the incumbent, so it is the
thing to beat: a pixel resolver that does not beat it is not worth its two
gigabytes of wheels, however principled its method.

Copied rather than imported, for one reason: the bench has to run in a CI
with no saknussemm (it is not published yet -- Phase 3 is blocked on the
maintainer), and an engine the loop cannot run everywhere is an engine the
loop does not have. The copy is pinned against the original by
``tests/test_baseline_is_saknussemms.py``, which skips when saknussemm is
absent and runs everywhere it matters -- starting with the machine
measurements are actually taken on.

AUTOPILOT carries the rule that follows from that: a measurement taken in an
environment where the parity test SKIPPED is not a measurement.
"""

from __future__ import annotations

import re

from hans.geometry import GeometryRequest, WordBox

#: U+00A0, U+202F, U+2007 -- the no-break spaces, which are NOT token
#: separators: saknussemm keeps them inside a String's CONTENT because an SP
#: element carries no content and would flatten them to an ordinary space.
#: Spelled as escapes because they are invisible in a listing.
_NO_BREAK_SPACES = "   "
_BREAKING_WS = re.compile(rf"[^\S{_NO_BREAK_SPACES}]+")


def is_space_token(token: str) -> bool:
    return _BREAKING_WS.fullmatch(token) is not None


def compute_geometry(
    hpos: int, width: int, tokens: list[str]
) -> list[tuple[str, int, int]]:
    """Widths proportional to a per-token weight; spaces weigh 0.6x.

    Verbatim from saknussemm, cumulative rounding and min-1 floor included.
    Do not "improve" it here: its job is to be what saknussemm does, and any
    divergence makes the comparison meaningless rather than favourable.
    """
    if not tokens:
        return []

    def _weight(t: str) -> float:
        return len(t) * 0.6 if is_space_token(t) else float(len(t))

    weights = [_weight(t) for t in tokens]
    total_weight = sum(weights)
    if total_weight == 0:
        per = width // len(tokens)
        return [(t, hpos + i * per, per) for i, t in enumerate(tokens)]

    unit = width / total_weight

    widths: list[int] = []
    cumulative = 0.0
    prev_rounded = 0
    for w in weights:
        cumulative += w * unit
        rounded = round(cumulative)
        widths.append(rounded - prev_rounded)
        prev_rounded = rounded

    if min(widths) < 1:
        deficit = 0
        for i, w in enumerate(widths):
            if w < 1:
                deficit += 1 - w
                widths[i] = 1
        while deficit > 0:
            donor = max(range(len(widths)), key=lambda i: widths[i])
            if widths[donor] <= 1:
                break
            take = min(deficit, widths[donor] - 1)
            widths[donor] -= take
            deficit -= take

    result: list[tuple[str, int, int]] = []
    cursor = hpos
    for t, w in zip(tokens, widths):
        result.append((t, cursor, w))
        cursor += w
    return result


class ProportionalResolver:
    """saknussemm's shipping behaviour, wearing the resolver interface."""

    name = "proportional (saknussemm)"

    def resolve(self, request: GeometryRequest) -> tuple[WordBox, ...]:
        geo = compute_geometry(request.hpos, request.width, list(request.tokens))
        return tuple(WordBox(text=t, hpos=h, width=w) for t, h, w in geo)
