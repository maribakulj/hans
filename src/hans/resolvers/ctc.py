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

from hans.cuts import LineCuts, transfer
from hans.geometry import GeometryRequest, WordBox


class MissingLine(LookupError):
    """The cache has nothing for this line."""


class CTCCutsResolver:
    """Word boxes from a recogniser's own character cuts."""

    def __init__(self, cuts: dict[str, LineCuts], *, name: str | None = None):
        self._cuts = cuts
        self.name = name or "ctc cuts (catmus-print)"

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
        return transfer(read, request.tokens, request.hpos, request.width)
