"""The two shapes everything here speaks in: a word's box, and a request.

Horizontal only, and deliberately so. A CTC forced alignment localises along
ONE axis -- the time axis of the emissions, which is the image's x axis once
the line is rectified. The vertical extent of a word inside its line is the
line's own extent until a mask says otherwise (that is G4, not G1), so
inventing a per-word VPOS here would be fabricating precision the method
does not have.

``GeometryRequest`` is shaped to match the seam it will plug into --
saknussemm's slow path calls ``_compute_geometry(hpos, width, tokens)`` at
``formats/alto/rewriter.py:1037`` and needs back one (token, hpos, width)
triple per token, spaces included. Keeping the shapes identical is what
makes the resolver droppable into that call site without adapting anything.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WordBox:
    """A token and the horizontal span it occupies.

    ``text`` may be a run of whitespace: the seam emits ``SP`` elements from
    space tokens and their geometry has to agree with the words around them,
    so spaces are first-class here rather than gaps between boxes.
    """

    text: str
    hpos: int
    width: int

    @property
    def right(self) -> int:
        return self.hpos + self.width


@dataclass(frozen=True)
class GeometryRequest:
    """One line's worth of work: a box, and the tokens that must fill it.

    ``image`` is an OPAQUE reference. The bench never opens it and the
    baseline resolver never looks at it; only a pixel resolver does. Typing
    it as ``object | None`` is what lets the request cross saknussemm's
    pixel-blind core untouched -- the core hands it over without importing
    anything that can decode an image.
    """

    hpos: int
    width: int
    tokens: tuple[str, ...]
    line_id: str = ""
    vpos: int = 0
    height: int = 0
    image: object | None = None
