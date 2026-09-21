"""The verdict is arithmetic. These tests are what keep it arithmetic."""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest

from hans.measure import Report
from hans.verdict import (
    FROZEN_CRITERION,
    CorpusOutcome,
    Outcome,
    decide,
)


def _report(within: float, worst: float, name: str = "r") -> Report:
    return Report(name, 1, 100, 0, 0.0, 0.0, 0.0, worst, 0.0, within)


def _outcome(corpus: str, base: float, cand: float, *, worst=(10.0, 10.0)):
    return CorpusOutcome(corpus, _report(base, worst[0]), _report(cand, worst[1]))


def test_the_frozen_criterion_is_the_one_in_autopilot() -> None:
    """The experiment is the text in AUTOPILOT; the code must not drift off it.

    Compared with accents stripped: the source keeps the criterion ASCII so
    it survives any encoding, AUTOPILOT is written for a human to read.
    """

    def flat(s: str) -> str:
        s = unicodedata.normalize("NFD", s)
        s = "".join(c for c in s if not unicodedata.combining(c))
        for ch in ("*", ">", "\u2019"):
            s = s.replace(ch, "" if ch != ">" else " ")
        s = s.lower().replace("'", " ")
        return " ".join(s.split())

    autopilot = (Path(__file__).parent.parent / "AUTOPILOT.md").read_text(
        encoding="utf-8"
    )
    assert flat(FROZEN_CRITERION) in flat(autopilot)


def test_two_corpora_cannot_declare_h1() -> None:
    """'Deux sur trois' is not satisfiable with two.

    This is the guard that stops a campaign short of its own criterion from
    being written up as a result.
    """
    v = decide([_outcome("a", 0.80, 0.95), _outcome("b", 0.80, 0.95)])
    assert v.outcome is Outcome.INCOMPLETE


def test_halving_on_two_of_three_confirms() -> None:
    v = decide(
        [
            _outcome("a", 0.80, 0.90),  # 20% -> 10%, halved
            _outcome("b", 0.90, 0.95),  # 10% -> 5%, halved
            _outcome("c", 0.90, 0.91),  # not halved
        ]
    )
    assert v.outcome is Outcome.CONFIRMED
    assert "2/3" in v.reason


def test_one_of_three_refutes() -> None:
    v = decide(
        [
            _outcome("a", 0.80, 0.90),
            _outcome("b", 0.90, 0.91),
            _outcome("c", 0.90, 0.91),
        ]
    )
    assert v.outcome is Outcome.REFUTED


def test_a_worsened_tail_refutes_whatever_the_average_says() -> None:
    """Fixing the middle while wrecking the tail is not a win.

    A boundary several characters out is a box drawn around the wrong word,
    which is the failure the whole project exists to repair.
    """
    v = decide(
        [
            _outcome("a", 0.80, 0.95, worst=(10.0, 40.0)),
            _outcome("b", 0.80, 0.95),
            _outcome("c", 0.80, 0.95),
        ]
    )
    assert v.outcome is Outcome.REFUTED
    assert "pire cas" in v.reason


@pytest.mark.parametrize("cand", [0.925, 0.9629])
def test_the_boundary_of_the_rule_is_exact(cand: float) -> None:
    """92.6% baseline -> 7.4% beyond -> must reach 3.7% beyond, i.e. 96.3%.

    Both of these are BELOW the bar and must not pass. Pinned because an
    off-by-one in the halving direction is the one arithmetic slip that
    would silently confirm H1.
    """
    v = decide([_outcome(str(i), 0.926, cand) for i in range(3)])
    assert v.outcome is Outcome.REFUTED


def test_exactly_halved_passes() -> None:
    v = decide([_outcome(str(i), 0.926, 0.963) for i in range(3)])
    assert v.outcome is Outcome.CONFIRMED
