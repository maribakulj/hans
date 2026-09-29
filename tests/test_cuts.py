"""The transfer that the H1 verdict rests on.

``transfer`` and ``support`` decided a published conclusion while nothing
exercised them. These tests state what they promise, one property per test,
so that a change which quietly breaks one is a red suite rather than a
different verdict.
"""

from __future__ import annotations

from itertools import pairwise

import pytest

from hans.cuts import LineCuts, learn_char_widths, support, transfer

# "de la" read perfectly: one span per character, ink-tight.
READ = LineCuts(
    line_id="L1",
    text="de la",
    spans=((100, 118), (118, 130), (130, 140), (140, 152), (152, 170)),
)
TOKENS = ("de", " ", "la")
HPOS, WIDTH = 100, 80


def _invariants(boxes, tokens, hpos, width):
    assert [b.text for b in boxes] == list(tokens)
    assert all(b.width >= 1 for b in boxes)
    assert all(a.hpos + a.width <= b.hpos for a, b in pairwise(boxes)), (
        "boxes must not overlap"
    )
    assert boxes[0].hpos >= hpos
    assert boxes[-1].hpos + boxes[-1].width <= hpos + width


def test_spans_mismatch_is_refused_at_construction() -> None:
    with pytest.raises(ValueError):
        LineCuts(line_id="L1", text="abc", spans=((0, 1),))


def test_a_clean_read_puts_the_boundary_on_the_ink_gap() -> None:
    boxes = transfer(READ, TOKENS, HPOS, WIDTH)
    _invariants(boxes, TOKENS, HPOS, WIDTH)
    assert (boxes[1].hpos, boxes[1].hpos + boxes[1].width) == (130, 140)


def test_the_space_box_is_exactly_what_the_words_left() -> None:
    """Derived from the words, so the two can never contradict each other.

    The space's span is what the bench reads as the predicted boundary; if
    it were computed independently it could disagree with the word boxes it
    sits between, and the ALTO would say two different things at once.
    """
    boxes = transfer(READ, TOKENS, HPOS, WIDTH)
    assert boxes[1].hpos == boxes[0].hpos + boxes[0].width
    assert boxes[1].hpos + boxes[1].width == boxes[2].hpos


def test_case_and_accents_do_not_stop_the_match() -> None:
    """Small capitals cost 168px before folding existed."""
    read = LineCuts("L1", "DE LA", READ.spans)
    boxes = transfer(read, TOKENS, HPOS, WIDTH)
    assert (boxes[1].hpos, boxes[1].hpos + boxes[1].width) == (130, 140)

    accented = LineCuts("L1", "dé la", READ.spans)
    assert transfer(accented, ("de", " ", "la"), HPOS, WIDTH)[1].hpos == 130


def test_unmatched_characters_are_interpolated_between_their_anchors() -> None:
    """The proportional assumption, but only across what could not be read.

    ``de XX la`` against a reading of ``de ?? la``: the two unknown
    characters get the span between the anchors around them, not a share of
    the whole line.
    """
    read = LineCuts(
        "L1",
        "de ?? la",
        (
            (100, 118),
            (118, 130),
            (130, 140),
            (140, 150),
            (150, 160),
            (160, 170),
            (170, 182),
            (182, 200),
        ),
    )
    boxes = transfer(read, ("de", " ", "XX", " ", "la"), 100, 100)
    _invariants(boxes, ("de", " ", "XX", " ", "la"), 100, 100)
    assert 130 <= boxes[2].hpos < boxes[2].hpos + boxes[2].width <= 175


def test_a_reading_that_shares_nothing_still_returns_valid_geometry() -> None:
    """Invalid geometry would be dropped wholesale by saknussemm's guard.

    A line the resolver cannot explain must still come back admissible —
    the caller decides whether to use it, via ``support``, not by catching
    a malformed answer.
    """
    read = LineCuts("L1", "zzzzz", READ.spans)
    boxes = transfer(read, TOKENS, HPOS, WIDTH)
    _invariants(boxes, TOKENS, HPOS, WIDTH)


def test_a_box_narrower_than_its_tokens_still_yields_one_pixel_each() -> None:
    """Degenerate, but it must not produce a zero-width String."""
    tokens = ("a", " ", "b", " ", "c")
    read = LineCuts("L1", "a b c", tuple((i, i + 1) for i in range(5)))
    boxes = transfer(read, tokens, 0, 5)
    _invariants(boxes, tokens, 0, 5)


@pytest.mark.parametrize(
    "read_text,target,expected",
    [
        ("de la", "de la", 1.0),
        ("DE LA", "de la", 1.0),
        ("de la", "", 0.0),
        ("zzzzz", "de la", 0.0),
    ],
)
def test_support_measures_what_the_reading_can_anchor(
    read_text: str, target: str, expected: float
) -> None:
    read = LineCuts("L1", read_text, tuple((i, i + 1) for i in range(len(read_text))))
    assert support(read, target) == pytest.approx(expected, abs=0.25)


def test_support_sees_fraktur_coming_but_only_just() -> None:
    """The finding that refuted H1, pinned as a number.

    A French-print model reading Fraktur produces a text that still shares
    enough characters to clear a 0.5 threshold — which is exactly why the
    threshold did not save the two boundaries that lost H1.
    """
    alto = "die durch die Bedürfnisse der Zeit und des"
    read_text = "bie burd bie Seburfniffe ber Jeit unb bes"
    read = LineCuts("L1", read_text, tuple((i, i + 1) for i in range(len(read_text))))
    s = support(read, alto)
    assert 0.5 <= s < 0.7, s


def test_character_width_learning_is_scale_invariant() -> None:
    reads = [
        LineCuts("small", "Wi", ((0, 20), (20, 25))),
        LineCuts("large", "Wi", ((0, 40), (40, 50))),
    ]
    widths = learn_char_widths(reads)
    assert widths["w"] == pytest.approx(1.6)
    assert widths["i"] == pytest.approx(0.4)
    assert widths["w"] / widths["i"] == pytest.approx(4.0)


def test_weighted_gap_moves_only_the_boundary_inside_the_same_anchors() -> None:
    """Wide inserted glyphs should get more of an uncertain interval.

    The recogniser anchors ``a`` at [0,10] and ``ib`` at [30,45].  The
    corrected text inserts ``W `` between them. Equal interpolation gives
    W and the space 10 px each; learned widths 4:1 give 16 px and 4 px.
    The outer anchors themselves must not move.
    """
    read = LineCuts(
        "L1",
        "a??ib",
        ((0, 10), (10, 20), (20, 30), (30, 35), (35, 45)),
    )
    tokens = ("aW", " ", "ib")
    plain = transfer(read, tokens, 0, 45)
    weighted = transfer(
        read, tokens, 0, 45, char_widths={"w": 4.0, " ": 1.0}
    )

    assert (plain[1].hpos, plain[1].width) == (20, 10)
    assert (weighted[1].hpos, weighted[1].width) == (26, 4)
    assert weighted[0].hpos == plain[0].hpos == 0
    assert weighted[-1].hpos + weighted[-1].width == 45
