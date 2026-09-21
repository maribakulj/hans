"""Reading reference word geometry out of ALTO.

The bench's only XML, and it stays small on purpose: this module must NOT
share code with the thing being measured. saknussemm has a real ALTO parser;
using it here would mean a bug in that parser could make the bench agree
with the defendant for the wrong reason.

Namespaces are matched by local name. ALTO ships as v2, v3 and v4 with
different namespace URIs, and the corpora at hand include one file with no
namespace at all (``corpus/37-GT-BNL``), so binding a prefix would silently
read zero lines from a third of the material.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from lxml import etree

from hans.geometry import WordBox


@dataclass(frozen=True)
class ReferenceLine:
    """A line whose word boxes are taken as ground truth.

    "Ground truth" here means: whatever the producer of this ALTO wrote. The
    bench never asks whether those boxes are RIGHT in an absolute sense --
    it asks whether a resolver can recover them after they have been
    mechanically destroyed. That is a weaker claim than "correct geometry",
    and it is the honest one: it needs no annotation campaign, and a
    resolver that scores well against it is reproducing the producer's own
    segmentation, which is exactly what a repair is meant to do.
    """

    line_id: str
    hpos: int
    vpos: int
    width: int
    height: int
    words: tuple[WordBox, ...]


def _local(el: etree._Element) -> str:
    return str(etree.QName(el).localname)


def _int(el: etree._Element, name: str) -> int | None:
    raw = el.get(name)
    if raw is None:
        return None
    try:
        # ALTO writes coordinates as floats often enough ("123.0"); truncate
        # toward zero, which is what saknussemm's parser does too.
        return int(float(raw))
    except ValueError:
        return None


def read_lines(path: Path | str, *, min_words: int = 2) -> list[ReferenceLine]:
    """Every TextLine carrying complete word-level geometry.

    A line is skipped -- never repaired, never guessed -- when any String
    lacks HPOS or WIDTH, when it holds fewer than ``min_words`` words, or
    when its words are not left-to-right monotonic. A line the bench cannot
    read exactly is a line the bench must not score: silently admitting a
    half-measured line is how a corpus starts flattering whoever measures
    it.
    """
    tree = etree.parse(str(path))
    lines: list[ReferenceLine] = []

    for el in tree.iter():
        if not isinstance(el.tag, str) or _local(el) != "TextLine":
            continue

        words: list[WordBox] = []
        broken = False
        for child in el:
            if not isinstance(child.tag, str) or _local(child) != "String":
                continue
            hpos, width = _int(child, "HPOS"), _int(child, "WIDTH")
            content = child.get("CONTENT")
            if hpos is None or width is None or not content or width <= 0:
                broken = True
                break
            words.append(WordBox(text=content, hpos=hpos, width=width))

        if broken or len(words) < min_words:
            continue

        # Monotonic left-to-right, or the notion of "the gap between word i
        # and word i+1" has no meaning and every boundary measured on this
        # line would be noise. Right-to-left scripts are not handled yet and
        # must not be scored as if they were.
        if any(b.hpos < a.hpos for a, b in pairwise(words)):
            continue

        line_hpos = _int(el, "HPOS")
        line_width = _int(el, "WIDTH")
        if line_hpos is None or line_width is None or line_width <= 0:
            # Derive the line box from its words rather than drop the line:
            # the 37-GT-BNL ALTO puts geometry on Strings and not always on
            # the TextLine, and those pages are a third of the material.
            line_hpos = words[0].hpos
            line_width = words[-1].right - line_hpos

        lines.append(
            ReferenceLine(
                line_id=el.get("ID") or f"line-{len(lines)}",
                hpos=line_hpos,
                vpos=_int(el, "VPOS") or 0,
                width=line_width,
                height=_int(el, "HEIGHT") or 0,
                words=tuple(words),
            )
        )

    return lines
