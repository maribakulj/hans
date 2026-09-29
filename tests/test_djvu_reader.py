"""Le lecteur DjVu XML (Internet Archive) : mêmes règles que le lecteur ALTO."""

from __future__ import annotations

from pathlib import Path

from hans.alto import read_djvu_lines

DJVU = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE DjVuXML>
<DjVuXML>
<BODY>
<OBJECT data="file://p1.djvu" type="image/x.djvu" height="3000" width="2000">
<HIDDENTEXT>
<PAGECOLUMN><REGION><PARAGRAPH>
<LINE>
<WORD coords="100,220,180,200">Les</WORD>
<WORD coords="200,220,320,200">devises</WORD>
<WORD coords="340,220,400,200">et</WORD>
</LINE>
<LINE>
<WORD coords="100,320,150,300">un</WORD>
</LINE>
<LINE>
<WORD coords="100,420,150,400">mal</WORD>
<WORD coords="x,420,220,400">formé</WORD>
</LINE>
</PARAGRAPH></REGION></PAGECOLUMN>
</HIDDENTEXT>
</OBJECT>
<OBJECT data="file://p2.djvu" type="image/x.djvu" height="3000" width="2000">
<HIDDENTEXT><PAGECOLUMN><REGION><PARAGRAPH>
<LINE>
<WORD coords="100,220,180,200">page</WORD>
<WORD coords="200,220,320,200">deux</WORD>
</LINE>
</PARAGRAPH></REGION></PAGECOLUMN></HIDDENTEXT>
</OBJECT>
</BODY>
</DjVuXML>
"""


def test_reads_words_with_their_horizontal_extent(tmp_path: Path) -> None:
    path = tmp_path / "book_djvu.xml"
    path.write_text(DJVU, encoding="utf-8")
    lines = read_djvu_lines(path)
    # the one-word line and the malformed line are skipped, like in ALTO
    assert [ln.line_id for ln in lines] == ["p1-l1", "p2-l1"]
    first = lines[0]
    assert [(w.text, w.hpos, w.width) for w in first.words] == [
        ("Les", 100, 80),
        ("devises", 200, 120),
        ("et", 340, 60),
    ]
    assert (first.hpos, first.width) == (100, 300)


def test_max_pages_stops_the_walk(tmp_path: Path) -> None:
    path = tmp_path / "book_djvu.xml"
    path.write_text(DJVU, encoding="utf-8")
    assert [ln.line_id for ln in read_djvu_lines(path, max_pages=1)] == ["p1-l1"]
