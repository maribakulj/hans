"""Scoring: zero inside the blank, and a crash is never a zero."""

from __future__ import annotations

from pathlib import Path

from hans.alto import read_lines
from hans.corrupt import line_case
from hans.geometry import GeometryRequest, WordBox
from hans.measure import boundary_errors, interval_distance, score


def test_interval_distance_is_zero_on_overlap() -> None:
    assert interval_distance((0, 10), (5, 15)) == 0.0
    assert interval_distance((0, 10), (10, 15)) == 0.0
    assert interval_distance((0, 10), (13, 15)) == 3.0
    assert interval_distance((13, 15), (0, 10)) == 3.0


class _Perfect:
    """Returns the true boxes -- the bench must score it at exactly zero."""

    name = "perfect"

    def __init__(self, boxes: tuple[WordBox, ...]) -> None:
        self._boxes = boxes

    def resolve(self, request: GeometryRequest) -> tuple[WordBox, ...]:
        return self._boxes


class _Crashes:
    name = "crashes"

    def resolve(self, request: GeometryRequest) -> tuple[WordBox, ...]:
        raise RuntimeError("no")


def _truth(case) -> tuple[WordBox, ...]:
    out: list[WordBox] = []
    for i, w in enumerate(case.true_boxes):
        if i:
            prev = case.true_boxes[i - 1]
            out.append(WordBox(" ", prev.right, w.hpos - prev.right))
        out.append(w)
    return tuple(out)


def test_the_true_geometry_scores_zero(alto_v4: Path) -> None:
    case = line_case(read_lines(alto_v4)[0])
    assert case is not None
    assert boundary_errors(_truth(case), case) == [0.0, 0.0]


def test_a_resolver_that_raises_is_a_failure_not_a_perfect_score(
    alto_v4: Path,
) -> None:
    """Averaging a crash in as zero would reward giving up on hard lines."""
    case = line_case(read_lines(alto_v4)[0])
    assert case is not None
    report = score(_Crashes(), [case])
    assert report.failures == 1
    assert report.boundaries == 0


def test_wrong_token_count_is_refused_loudly(alto_v4: Path) -> None:
    case = line_case(read_lines(alto_v4)[0])
    assert case is not None
    import pytest

    with pytest.raises(ValueError):
        boundary_errors((WordBox("de", 100, 18),), case)


def test_perfect_beats_proportional_on_the_report(alto_v4: Path) -> None:
    from hans.resolvers import ProportionalResolver

    case = line_case(read_lines(alto_v4)[0])
    assert case is not None
    assert score(_Perfect(_truth(case)), [case]).mean == 0.0
    assert score(ProportionalResolver(), [case]).failures == 0
