"""The scale guard, which was wrong the first time it was written.

It stands between the campaign and the trap that has already cost
saknussemm two full measurement campaigns, twice: an ALTO in tenths of a
millimetre decoded as if it were in pixels crops 18% short, further off with
every line down the page, and returns text — plausible, never empty.

Its first version compared the rightmost LINE to the image width and would
have refused a perfectly scaled corpus at 1.247, because no line reaches the
page edge. A guard that cries wolf gets switched off, so its false-positive
behaviour is pinned here too.

Importable without kraken: the heavy imports live inside ``main``.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "decode_lines", Path(__file__).parent.parent / "tools" / "decode_lines.py"
)
assert _SPEC and _SPEC.loader
decode = importlib.util.module_from_spec(_SPEC)
sys.modules["decode_lines"] = decode
_SPEC.loader.exec_module(decode)


@dataclass
class _Line:
    hpos: int
    width: int


def _lines(right_edge: int) -> list[_Line]:
    return [_Line(hpos=10, width=right_edge - 10)]


def test_a_declared_page_width_that_agrees_passes() -> None:
    decode._check_scale(_lines(1403), img_width=1749, scale=1.0, page_width=1749)


def test_lines_falling_short_of_the_page_edge_are_not_a_mismatch() -> None:
    """The false positive that would have disabled this guard.

    The rightmost line ends at 1403 on a 1749px page — an implied 1.247 —
    while the page itself declares 1749 and the scale really is 1.
    """
    decode._check_scale(_lines(1403), img_width=1749, scale=1.0, page_width=1749)


def test_an_unverifiable_scale_is_refused_rather_than_guessed() -> None:
    """No declared page width and no --scale: the guard must not default to 1.

    This is the regression the suite exists for. The guard's second version
    widened its tolerance to kill a false positive and, with it, silently
    stopped refusing the tenths-of-a-millimetre corpus it was written for.
    """
    with pytest.raises(SystemExit) as exc:
        decode._check_scale(
            _lines(741),
            img_width=875,
            scale=1.0,
            page_width=None,
            scale_was_given=False,
        )
    assert "INVERIFIABLE" in str(exc.value)


def test_a_stated_scale_is_accepted_when_nothing_can_verify_it() -> None:
    """The operator asserts it; the implied bound is printed for the record.

    The line extent cannot arbitrate: 37-GT-BNL implies 1.181 with a true
    scale of 1.181, the pinned Gallica implies 1.247 with a true scale of
    1.0. Guessing between those is how a guard starts being wrong.
    """
    decode._check_scale(
        _lines(741),
        img_width=875,
        scale=1.1811,
        page_width=None,
        scale_was_given=True,
    )


def test_a_declared_width_is_held_to_a_tighter_tolerance() -> None:
    """When the ALTO states its page size there is nothing to guess."""
    with pytest.raises(SystemExit):
        decode._check_scale(_lines(1000), img_width=1749, scale=1.0, page_width=1500)


def test_a_declared_width_that_agrees_within_2_percent_passes() -> None:
    decode._check_scale(_lines(1000), img_width=1760, scale=1.0, page_width=1749)


@pytest.mark.parametrize(
    "cut,expected",
    [
        ([[10, 0], [20, 0], [20, 5], [10, 5]], [10, 20, 20, 10]),
        ([3, 9], [3, 9]),
    ],
)
def test_xs_reads_both_shapes_kraken_returns(cut: object, expected: list[int]) -> None:
    assert decode._xs(cut) == expected
