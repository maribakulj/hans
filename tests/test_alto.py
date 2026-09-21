"""The reader admits a line only when it can measure it exactly."""

from __future__ import annotations

from pathlib import Path

from hans.alto import read_lines


def test_reads_a_complete_line(alto_v4: Path) -> None:
    lines = read_lines(alto_v4)
    assert [line.line_id for line in lines] == ["L1"]
    assert [w.text for w in lines[0].words] == ["de", "la", "Republique"]
    assert lines[0].words[0].right == 118


def test_namespace_is_matched_by_local_name(alto_v4: Path, alto_bare: Path) -> None:
    """A bare ALTO must read identically to a namespaced one.

    Not a hypothetical: corpus/37-GT-BNL has no namespace, and it is a third
    of the material on hand.
    """
    assert read_lines(alto_bare) == read_lines(alto_v4)


def test_a_line_with_one_word_has_no_boundary_to_score(alto_v4: Path) -> None:
    assert all(line.line_id != "L2" for line in read_lines(alto_v4))


def test_a_string_without_geometry_disqualifies_its_line(alto_v4: Path) -> None:
    """Never repaired, never guessed -- dropped.

    Admitting a half-measured line is how a corpus starts flattering
    whoever measures it.
    """
    assert all(line.line_id != "L3" for line in read_lines(alto_v4))
