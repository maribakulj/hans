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


#: Sequences that only appear when UTF-8 bytes were decoded as Latin-1.
#: "é" (0xC3 0xA9) read as Latin-1 becomes "Ã©", so a lone "Ã" or "Â" before
#: another non-ASCII character is the signature.
_MOJIBAKE_MARKERS = ("\u00c3", "\u00c2")


def repair_mojibake(text: str) -> str:
    """Undo a UTF-8 payload that was read through a Latin-1 declaration.

    The pinned Gallica ALTO declare ``encoding="ISO-8859-1"`` and hold UTF-8,
    so a conforming parser hands back "raisonnÃ©e" for "raisonnée". Left
    alone this does not merely look wrong -- it would BIAS the campaign. The
    proportional resolver never looks at the text, so mojibake costs it
    nothing; a pixel resolver reads the page correctly and would then be
    scored on its failure to match a corrupted target. The candidate would
    lose for being right.

    Repaired only when the telltale sequence is present AND the round-trip
    is lossless, so text that is genuinely about "Ãland" survives.
    """
    if not any(m in text for m in _MOJIBAKE_MARKERS):
        return text
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


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
            words.append(WordBox(text=repair_mojibake(content), hpos=hpos, width=width))

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


def read_page_lines(path: Path | str, *, min_words: int = 2) -> list[ReferenceLine]:
    """Les lignes d'un PAGE XML, avec la géométrie de ses ``Word``.

    Même contrat que :func:`read_lines` : une ligne n'est admise que si tous
    ses mots portent une géométrie exploitable. PAGE donne des polygones
    (``Coords points="x,y x,y ..."``) et non des rectangles ; on prend
    l'enveloppe horizontale, qui est tout ce que ce banc mesure.
    """
    tree = etree.parse(str(path))
    lines: list[ReferenceLine] = []

    def extent(el: etree._Element) -> tuple[int, int, int, int] | None:
        for c in el:
            if not isinstance(c.tag, str) or _local(c) != "Coords":
                continue
            pts = []
            for pair in (c.get("points") or "").split():
                try:
                    x, y = pair.split(",")
                    pts.append((int(float(x)), int(float(y))))
                except ValueError:
                    return None
            if not pts:
                return None
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            return min(xs), min(ys), max(xs), max(ys)
        return None

    for el in tree.iter():
        if not isinstance(el.tag, str) or _local(el) != "TextLine":
            continue
        words: list[WordBox] = []
        broken = False
        for child in el:
            if not isinstance(child.tag, str) or _local(child) != "Word":
                continue
            box = extent(child)
            text = None
            for te in child:
                if isinstance(te.tag, str) and _local(te) == "TextEquiv":
                    for u in te:
                        if isinstance(u.tag, str) and _local(u) == "Unicode":
                            text = u.text
            if box is None or not text or box[2] <= box[0]:
                broken = True
                break
            words.append(
                WordBox(
                    text=repair_mojibake(text), hpos=box[0], width=box[2] - box[0]
                )
            )
        if broken or len(words) < min_words:
            continue
        if any(b.hpos < a.hpos for a, b in pairwise(words)):
            continue
        lb = extent(el)
        if lb is None:
            continue
        lines.append(
            ReferenceLine(
                line_id=el.get("id") or el.get("ID") or f"line-{len(lines)}",
                hpos=lb[0],
                vpos=lb[1],
                width=lb[2] - lb[0],
                height=lb[3] - lb[1],
                words=tuple(words),
            )
        )
    return lines
