"""What the geometric triage promises, one property per test.

Every fixture is a synthetic ALTO built from a list of boxes, so each test
names the one defect it plants and nothing else changes between the
accepted page and the refused one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hans.triage import Thresholds, column_width, read_boxes, triage

PITCH, HEIGHT = 40, 30


def _alto(boxes: list[tuple[int, int, int, int]], width: int = 3000) -> str:
    lines = "".join(
        f'<TextLine ID="l{i}" HPOS="{x}" VPOS="{y}" WIDTH="{w}" HEIGHT="{h}">'
        f'<String CONTENT="mot"/></TextLine>'
        for i, (x, y, w, h) in enumerate(boxes)
    )
    return (
        '<alto xmlns="http://www.loc.gov/standards/alto/ns-v3#"><Layout>'
        f'<Page WIDTH="{width}" HEIGHT="4000"><PrintSpace><TextBlock>'
        f"{lines}</TextBlock></PrintSpace></Page></Layout></alto>"
    )


def _columns(n_lines: int = 40, starts: tuple[int, ...] = (200, 1500)) -> list:
    """``n_lines`` per column, read column by column, top to bottom."""
    return [(x, 100 + i * PITCH, 1100, HEIGHT) for x in starts for i in range(n_lines)]


@pytest.fixture
def write(tmp_path: Path):
    def _write(boxes, **kw) -> Path:
        p = tmp_path / "page.xml"
        p.write_text(_alto(boxes, **kw), encoding="utf-8")
        return p

    return _write


def test_a_clean_two_column_page_is_accepted(write):
    v = triage(write(_columns()))
    assert v.accepted and v.reasons == []
    assert v.column_width == 1300
    assert v.fused == v.wide == v.disorder == v.gaps == 0.0
    assert v.uncovered is None


def test_fused_lines_are_refused_by_height(write):
    boxes = _columns()
    for i in range(0, 80, 10):  # 10 % of lines are three lines tall
        x, y, w, _ = boxes[i]
        boxes[i] = (x, y, w, 3 * HEIGHT)
    v = triage(write(boxes))
    assert not v.accepted and v.fused == pytest.approx(0.10)
    assert any("plus hautes" in r for r in v.reasons)


def test_a_column_swallowed_into_its_neighbour_is_refused_by_width(write):
    boxes = _columns()
    for i in range(0, 80, 10):  # 10 % of lines span both columns
        _, y, _, h = boxes[i]
        boxes[i] = (200, y, 2400, h)
    v = triage(write(boxes))
    assert not v.accepted and v.wide == pytest.approx(0.10)
    assert any("plus larges" in r for r in v.reasons)


def test_a_shuffled_reading_order_is_refused(write):
    boxes = _columns()
    boxes[:40] = boxes[:40][::-1]  # first column read bottom-up
    v = triage(write(boxes))
    assert not v.accepted and v.disorder > 0.10
    assert any("rebours" in r for r in v.reasons)


def test_lines_the_ocr_never_produced_are_refused_by_gaps(write):
    # Runs of four lines missing: the transition across each hole jumps
    # five pitches, well past the ratio of three.
    boxes = [b for i, b in enumerate(_columns(60)) if i % 8 >= 4]
    v = triage(write(boxes))
    assert not v.accepted and v.gaps > 0.10
    assert any("sauts verticaux" in r for r in v.reasons)


def test_an_indented_theatre_page_is_one_column_not_two(write):
    """A speaker name sits alone at the left margin above each indented
    speech; those short lines open a second group of left edges, which is
    not a column. Bruyère and Molière were refused for 59–67 % of lines
    'too wide' before the estimate checked itself against the lines."""
    boxes = []
    for i in range(30):
        y = 100 + i * PITCH
        if i % 3 == 0:
            boxes.append((300, y, 500, HEIGHT))  # « DORANTE. »
        else:
            boxes.append((1000, y, 2000, HEIGHT))  # the verse
    page = read_boxes(write(boxes))
    assert column_width(page) == 2700  # the text block, not the indent
    v = triage(write(boxes))
    assert v.accepted, v.reasons


def test_two_real_columns_keep_their_spacing(write):
    page = read_boxes(write(_columns(starts=(200, 1400, 2600)), width=4000))
    assert column_width(page) == 1200


def test_fewer_than_two_lines_is_refused(write):
    v = triage(write([(200, 100, 1000, HEIGHT)]))
    assert not v.accepted and v.reasons == ["moins de deux lignes"]


def test_thresholds_are_the_knobs(write):
    boxes = _columns()
    for i in range(0, 80, 10):
        x, y, w, _ = boxes[i]
        boxes[i] = (x, y, w, 3 * HEIGHT)
    assert not triage(write(boxes)).accepted
    assert triage(write(boxes), thresholds=Thresholds(max_fused=0.2)).accepted


def test_page_xml_polygons_are_read_too(tmp_path: Path):
    p = tmp_path / "page.xml"
    p.write_text(
        '<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15">'
        '<Page imageWidth="3000" imageHeight="4000"><TextRegion>'
        '<TextLine id="l1"><Coords points="200,100 1300,100 1300,130 200,130"/>'
        "<TextEquiv><Unicode>mot</Unicode></TextEquiv></TextLine>"
        '<TextLine id="l2"><Coords points="200,140 1300,140 1300,170 200,170"/>'
        "<TextEquiv><Unicode>mot</Unicode></TextEquiv></TextLine>"
        "</TextRegion></Page></PcGts>",
        encoding="utf-8",
    )
    page = read_boxes(p)
    assert [(ln.hpos, ln.vpos, ln.width, ln.height) for ln in page.lines] == [
        (200, 100, 1100, 30),
        (200, 140, 1100, 30),
    ]
    assert page.lines[0].text == "mot"
