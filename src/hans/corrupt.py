"""Manufacturing 1-to-N cases whose ground truth is exact, not annotated.

The bench's whole claim rests on one asymmetry, so it is worth stating
plainly.

Take two adjacent words whose boxes the ALTO already gives: ``de`` at
x=100..118 and ``la`` at x=124..141. Glue them into ONE String ``dela``
whose box is the union, x=100..141. That union is **not a fabrication** --
it is exactly the box a producer that mis-segmented the line would have
drawn, and it is derived arithmetically from two boxes that were already
there. Now hand a resolver the union box and the correct segmentation
``["de", " ", "la"]`` and ask it where the boundary goes. The answer is
already known, to the pixel, and nobody chose it.

The reverse direction is NOT safe and the bench does not use it. To
manufacture a split case one would have to invent where inside ``dela`` the
fake producer cut -- and any rule for inventing it (proportional to
character count, say) is the very hypothesis the baseline resolver embodies.
The corpus would then be built out of the defendant's own assumption and the
baseline would win by construction. One direction gives free ground truth;
the other gives a rigged trial. Only the free one is here.

What this does NOT prove: that the recovered boundary is where a human
would put it, or that the producer's original boxes were any good. It
proves recovery of the producer's own segmentation, which is what a repair
owes and all a repair owes.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from hans.alto import ReferenceLine
from hans.geometry import GeometryRequest, WordBox


@dataclass(frozen=True)
class MergeCase:
    """One run of adjacent words glued into a single box.

    ``gaps`` holds, per internal boundary, the interval in which the true
    boundary lies: from the right edge of the left word to the left edge of
    the right one. It is an INTERVAL and not a point because every x inside
    the inter-word blank is an equally correct place to cut -- scoring
    against a single point would charge a resolver for landing in the middle
    of the gap instead of on one of its edges, which is not an error.
    """

    line_id: str
    first_index: int
    source_content: str
    tokens: tuple[str, ...]
    true_boxes: tuple[WordBox, ...]
    gaps: tuple[tuple[int, int], ...]
    box_hpos: int
    box_width: int

    def request(self, *, image: object | None = None) -> GeometryRequest:
        return GeometryRequest(
            hpos=self.box_hpos,
            width=self.box_width,
            tokens=self.tokens,
            line_id=self.line_id,
            image=image,
        )

    @property
    def mean_char_width(self) -> float:
        """Box width per character of the correct text, spaces included.

        The natural unit for a boundary error: "off by half a character" is
        a statement that survives a change of corpus, of resolution and of
        ALTO unit; "off by 9 pixels" is not. The 37-GT-BNL pages are in
        tenths of a millimetre and the BnF page is in pixels at 6436 wide --
        a shared pixel scale between them does not exist.
        """
        chars = sum(len(t) for t in self.tokens)
        return self.box_width / chars if chars else 0.0


def merge_cases(line: ReferenceLine, *, run: int = 2) -> list[MergeCase]:
    """Every window of ``run`` adjacent words on this line, glued.

    ``run=2`` is the ``dela`` -> ``de la`` case and the one to start from.
    Longer runs exist (``aujourdhui`` spanning three source words) and get
    harder in a way worth measuring separately, which is why the window is a
    parameter and the report keys on it.
    """
    if run < 2 or len(line.words) < run:
        return []

    cases: list[MergeCase] = []
    for i in range(len(line.words) - run + 1):
        window = line.words[i : i + run]

        # A window is only usable if its words really are disjoint and in
        # order: overlapping boxes make the "gap" a negative interval and
        # there is nothing to recover. Producers do emit those.
        if any(b.hpos < a.right for a, b in pairwise(window)):
            continue

        tokens: list[str] = []
        for j, w in enumerate(window):
            if j:
                tokens.append(" ")
            tokens.append(w.text)

        cases.append(
            MergeCase(
                line_id=line.line_id,
                first_index=i,
                source_content="".join(w.text for w in window),
                tokens=tuple(tokens),
                true_boxes=tuple(window),
                gaps=tuple((a.right, b.hpos) for a, b in pairwise(window)),
                box_hpos=window[0].hpos,
                box_width=window[-1].right - window[0].hpos,
            )
        )

    return cases


def cases_from_lines(lines: list[ReferenceLine], *, run: int = 2) -> list[MergeCase]:
    return [c for line in lines for c in merge_cases(line, run=run)]


def line_case(line: ReferenceLine) -> MergeCase | None:
    """The whole line re-tokenised -- what saknussemm's slow path ACTUALLY does.

    ``rewriter.py:1037`` calls ``_compute_geometry(hpos, text_width, tokens)``
    with the LINE's box and ALL its tokens: once a correction drops off the
    fast path, every original word box on that line is discarded and the
    width is redistributed from scratch. A bench that only glues two
    neighbours measures a repair nobody performs, and it measures it as
    easy -- the union of two adjacent boxes is pinned by two real edges a
    few characters apart, so there is almost no room to be wrong. Measured:
    99.8% of two-word boundaries land inside the true blank, against 92.6%
    for the real thing.

    Same manufacture, same exactness, wider window.
    """
    cases = merge_cases(line, run=len(line.words))
    return cases[0] if cases else None


def line_cases(lines: list[ReferenceLine]) -> list[MergeCase]:
    return [c for line in lines if (c := line_case(line)) is not None]
