"""Scoring a resolver against manufactured cases.

One number per boundary: how far the predicted cut fell from the interval
where the true cut lies. Zero when it landed anywhere inside the blank
between the two words -- see ``MergeCase.gaps`` for why that is not
leniency.

The report deliberately carries a distribution and not a mean. AUTOPILOT
rule 8 -- "un resultat qui va dans le sens espere demande plus de
verification qu'un resultat decevant" -- was paid for by a mean that looked
excellent while the text underneath was a regression. A mean boundary error
hides the case this project exists for: the resolver that is within half a
character on easy lines and three characters out on the split it was built
to repair. p90 and worst are what move when that happens.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Protocol

from hans.corrupt import MergeCase
from hans.geometry import GeometryRequest, WordBox


class Resolver(Protocol):
    """What every resolver is, baseline and pixel alike.

    Structurally identical to the seam saknussemm will expose, so a resolver
    written against this Protocol drops into the rewriter's slow path with
    no adapter.
    """

    name: str

    def resolve(self, request: GeometryRequest) -> tuple[WordBox, ...]: ...


def interval_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Gap between two intervals; 0.0 when they touch or overlap."""
    if a[1] < b[0]:
        return b[0] - a[1]
    if b[1] < a[0]:
        return a[0] - b[1]
    return 0.0


def boundary_errors(boxes: tuple[WordBox, ...], case: MergeCase) -> list[float]:
    """One error per internal boundary, in the case's own coordinate unit.

    The predicted boundary is read off the SPACE token's box, not off the
    word edges: the space is what the rewriter turns into an ``SP`` element,
    and its span IS the resolver's answer to "where does one word stop and
    the next begin". A resolver that returns no space token is scored on the
    point where the two word boxes meet instead.
    """
    if len(boxes) != len(case.tokens):
        raise ValueError(
            f"resolver returned {len(boxes)} boxes for {len(case.tokens)} tokens"
        )

    errors: list[float] = []
    for k, (start, end) in enumerate(case.gaps):
        # tokens alternate word, space, word, ... so boundary k is token 2k+1
        space = boxes[2 * k + 1]
        predicted = (
            (float(space.hpos), float(space.right))
            if space.width > 0
            else (float(space.hpos), float(space.hpos))
        )
        errors.append(interval_distance(predicted, (float(start), float(end))))

    return errors


@dataclass(frozen=True)
class Report:
    resolver: str
    cases: int
    boundaries: int
    failures: int
    mean: float
    median: float
    p90: float
    worst: float
    mean_chars: float
    within_half_char: float

    def line(self) -> str:
        return (
            f"{self.resolver:<24} n={self.boundaries:<6} "
            f"mean={self.mean:7.2f}  med={self.median:7.2f}  "
            f"p90={self.p90:7.2f}  worst={self.worst:8.2f}  "
            f"(mean={self.mean_chars:5.2f} char)  "
            f"<=0.5char: {self.within_half_char:5.1%}  "
            f"failed={self.failures}"
        )


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(q * (len(ordered) - 1) + 0.5))
    return ordered[idx]


def score(resolver: Resolver, cases: list[MergeCase]) -> Report:
    """Run a resolver over every case and reduce to one report.

    A resolver that raises is counted as a failure, never as a zero: an
    exception is a refusal to answer and averaging it in as a perfect score
    would reward crashing on the hard cases.
    """
    errors: list[float] = []
    normalised: list[float] = []
    failures = 0

    for case in cases:
        try:
            boxes = resolver.resolve(case.request())
            case_errors = boundary_errors(boxes, case)
        except Exception:  # noqa: BLE001 -- see docstring: ANY escape is a
            # refusal to answer. Narrowing this would let an unforeseen
            # failure mode inside a resolver abort the whole campaign
            # instead of being counted against that resolver.
            failures += 1
            continue
        errors.extend(case_errors)
        unit = case.mean_char_width
        if unit > 0:
            normalised.extend(e / unit for e in case_errors)

    if not errors:
        return Report(resolver.name, len(cases), 0, failures, 0, 0, 0, 0, 0, 0)

    return Report(
        resolver=resolver.name,
        cases=len(cases),
        boundaries=len(errors),
        failures=failures,
        mean=sum(errors) / len(errors),
        median=median(errors),
        p90=_percentile(errors, 0.90),
        worst=max(errors),
        mean_chars=sum(normalised) / len(normalised) if normalised else 0.0,
        within_half_char=(
            sum(1 for e in normalised if e <= 0.5) / len(normalised)
            if normalised
            else 0.0
        ),
    )
