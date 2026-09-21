"""The ground truth has to be arithmetic, or the bench is worthless."""

from __future__ import annotations

from pathlib import Path

from hans.alto import read_lines
from hans.corrupt import line_case, merge_cases


def test_the_glued_box_is_exactly_the_union(alto_v4: Path) -> None:
    """Nothing is invented: the box comes from two edges already in the ALTO.

    This is the property the whole method rests on. ``de`` starts at 100 and
    ``la`` ends at 141, so a producer that emitted ``dela`` as one String
    would have drawn 100..141 -- and the bench asks the resolver to recover
    a cut whose answer was fixed before anyone chose anything.
    """
    line = read_lines(alto_v4)[0]
    case = merge_cases(line, run=2)[0]
    assert (case.box_hpos, case.box_width) == (100, 41)
    assert case.source_content == "dela"
    assert case.tokens == ("de", " ", "la")
    assert case.gaps == ((118, 124),)


def test_tokens_alternate_word_space_word(alto_v4: Path) -> None:
    case = line_case(read_lines(alto_v4)[0])
    assert case is not None
    assert case.tokens == ("de", " ", "la", " ", "Republique")
    assert case.gaps == ((118, 124), (141, 147))


def test_the_whole_line_case_spans_the_whole_line(alto_v4: Path) -> None:
    """The faithful case: every original word box discarded at once."""
    case = line_case(read_lines(alto_v4)[0])
    assert case is not None
    assert (case.box_hpos, case.box_width) == (100, 300)


def test_overlapping_boxes_are_refused(alto_v4: Path) -> None:
    """An inverted gap is not a hard case, it is a meaningless one."""
    line = read_lines(alto_v4)[0]
    from dataclasses import replace

    from hans.geometry import WordBox

    overlapped = replace(
        line,
        words=(WordBox("de", 100, 40), WordBox("la", 124, 17)),
    )
    assert merge_cases(overlapped, run=2) == []
