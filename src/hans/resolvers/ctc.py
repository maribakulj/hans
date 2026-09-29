"""The candidate: word geometry taken from what the recogniser saw.

Reads a cut cache produced by ``tools/decode_lines.py`` -- one free decode
per line, with a horizontal span per character -- and carries those positions
onto the tokens it is asked about (see ``hans.cuts``).

Deliberately cache-backed rather than model-backed. Decoding is ~1.5 s a
line; a bench over three corpora would spend hours re-reading pages it
already read, and every run would measure a slightly different thing if the
decode were re-done. A cache also makes the campaign auditable after the
fact: the text the model produced is on disk next to the numbers it produced.
"""

from __future__ import annotations

import json
from pathlib import Path

from hans.cuts import LineCuts, learn_char_widths, support, transfer
from hans.geometry import GeometryRequest, WordBox
from hans.resolvers.proportional import ProportionalResolver


class MissingLine(LookupError):
    """The cache has nothing for this line."""


class CTCCutsResolver:
    """Word boxes from a recogniser's own character cuts."""

    #: Below this share of the target anchored in the reading, the line is
    #: handed back to the incumbent. Half is chosen because it is the point
    #: where the reading stops being evidence and starts being a coincidence
    #: — NOT tuned on the corpora, which would make the bench score a
    #: threshold fitted to it.
    MIN_SUPPORT = 0.5

    def __init__(
        self,
        cuts: dict[str, LineCuts],
        *,
        name: str | None = None,
        fallback: object | None = None,
        weighted_gaps: bool = False,
    ):
        self._cuts = cuts
        self.name = name or "ctc cuts (catmus-print)"
        # What the SEAM does when a resolver declines, reproduced here so the
        # bench measures the thing that would actually ship. Scoring a
        # refusal as a failure instead would let the candidate improve its
        # worst case simply by declining every hard line.
        self._fallback = fallback or ProportionalResolver()
        self._char_widths = learn_char_widths(cuts.values()) if weighted_gaps else None
        self.declined = 0

    @classmethod
    def from_cache(cls, path: Path | str, **kw: str) -> CTCCutsResolver:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        cuts = {
            line_id: LineCuts(
                line_id=line_id,
                text=entry["text"],
                spans=tuple((int(a), int(b)) for a, b in entry["spans"]),
            )
            for line_id, entry in raw["lines"].items()
        }
        return cls(cuts, **kw)

    def __len__(self) -> int:
        return len(self._cuts)

    def resolve(self, request: GeometryRequest) -> tuple[WordBox, ...]:
        """Raise rather than fall back when a line was never decoded.

        The bench counts an exception as a failure and never as a zero, so
        a cache that silently misses half a corpus shows up as a failure
        count instead of as a score computed on the easy half.
        """
        read = self._cuts.get(request.line_id)
        if read is None:
            raise MissingLine(request.line_id)
        if support(read, "".join(request.tokens)) < self.MIN_SUPPORT:
            self.declined += 1
            return self._fallback.resolve(request)  # type: ignore[attr-defined,no-any-return]
        return transfer(
            read,
            request.tokens,
            request.hpos,
            request.width,
            char_widths=self._char_widths,
        )


class WeightedCTCCutsResolver(CTCCutsResolver):
    """CTC cuts with document-learned relative character widths in gaps.

    Matched characters keep their measured spans. Only unmatched runs are
    redistributed, and only inside the same left/right anchors as the base
    resolver. The learned model therefore cannot move reliable geometry.
    """

    def __init__(
        self,
        cuts: dict[str, LineCuts],
        *,
        name: str | None = None,
        fallback: object | None = None,
    ):
        super().__init__(
            cuts,
            name=name or "ctc cuts + learned glyph widths",
            fallback=fallback,
            weighted_gaps=True,
        )
