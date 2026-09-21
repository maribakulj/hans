"""Carrying character positions from what the model READ to what it must WRITE.

The measured finding this module exists for: kraken's forced alignment is
broken for this model (both the deprecated `kraken.align` path and
`kraken.tasks.ForcedAlignmentTaskModel` return the same collapsed geometry),
while its ORDINARY decode returns per-character cuts that land where the
characters are. So the geometry does not come from forcing a known text onto
the emissions; it comes from decoding freely and then carrying the positions
across to the text we actually need boxes for.

That inversion is not a workaround, it is sturdier. Forcing a path makes the
model explain a transcription whether or not the pixels support it -- which
is exactly how a hallucinated word acquires a confident-looking box. Decoding
first and aligning after keeps the two questions apart: what is written
there, and where the words we were handed belong.

Everything here is pure Python and knows nothing about kraken, torch or
images. The heavy stack runs elsewhere (`tools/decode_lines.py`) and leaves a
JSON cache behind; this module reads it. That is what lets the bench, and the
loop's CI, stay installable without a 2 GB wheel.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from hans.geometry import WordBox


@dataclass(frozen=True)
class LineCuts:
    """What the recogniser read on one line, and where each character sat.

    ``spans[i]`` is the horizontal extent of ``text[i]`` in PAGE coordinates
    -- kraken's cuts are already absolute, so nothing is rescaled here.
    """

    line_id: str
    text: str
    spans: tuple[tuple[int, int], ...]

    def __post_init__(self) -> None:
        if len(self.text) != len(self.spans):
            raise ValueError(
                f"{self.line_id}: {len(self.text)} chars, {len(self.spans)} spans"
            )


def _char_positions(read: LineCuts, target: str) -> list[tuple[float, float] | None]:
    """One span per character of ``target``, or None where nothing matched.

    Matching is character-level between what was read and what must be
    written. The two differ for ordinary reasons -- the model resolves an
    apostrophe differently, the correction changed a word -- and the
    unmatched positions are filled in afterwards rather than guessed here.
    """
    out: list[tuple[float, float] | None] = [None] * len(target)
    matcher = SequenceMatcher(None, read.text, target, autojunk=False)
    for src, dst, size in matcher.get_matching_blocks():
        for k in range(size):
            x0, x1 = read.spans[src + k]
            out[dst + k] = (float(x0), float(x1))
    return out


def _fill_gaps(
    positions: list[tuple[float, float] | None], hpos: int, width: int
) -> list[tuple[float, float]]:
    """Interpolate the characters the alignment could not place.

    A run of unmatched characters is spread evenly between its anchors --
    the proportional assumption, but applied only across the few characters
    the model could not account for instead of across the whole line. Runs
    at either end lean on the line's own edges.
    """
    n = len(positions)
    if n == 0:
        return []
    left = float(hpos)
    right = float(hpos + width)

    filled: list[tuple[float, float]] = []
    i = 0
    while i < n:
        if positions[i] is not None:
            filled.append(positions[i])  # type: ignore[arg-type]
            i += 1
            continue
        j = i
        while j < n and positions[j] is None:
            j += 1
        start = positions[i - 1][1] if i > 0 else left  # type: ignore[index]
        end = positions[j][0] if j < n else right  # type: ignore[index]
        end = max(end, start)
        step = (end - start) / (j - i)
        for k in range(j - i):
            filled.append((start + k * step, start + (k + 1) * step))
        i = j
    return filled


def transfer(
    read: LineCuts, tokens: tuple[str, ...], hpos: int, width: int
) -> tuple[WordBox, ...]:
    """Boxes for ``tokens``, built from where the recogniser saw characters.

    The contract the rewriter's guard enforces is reproduced here rather
    than hoped for: one box per token, in order, widths >= 1, no overlap,
    the whole run inside the line box. A resolver that satisfies it only
    most of the time is a resolver whose good lines are indistinguishable
    from its bad ones.

    Word boxes come from their characters' extent; SPACE boxes are then the
    gaps BETWEEN them. That ordering matters: the space's span is what the
    bench reads as the predicted boundary, and deriving it from the words
    keeps it from contradicting them.
    """
    target = "".join(tokens)
    positions = _fill_gaps(_char_positions(read, target), hpos, width)

    # 1. word extents from their own characters
    bounds: list[tuple[float, float] | None] = []
    cursor = 0
    for token in tokens:
        span = positions[cursor : cursor + len(token)]
        cursor += len(token)
        if token.strip() and span:
            bounds.append((min(s[0] for s in span), max(s[1] for s in span)))
        else:
            bounds.append(None)

    # 2. spaces fill what the words left, so the two can never disagree
    for i, b in enumerate(bounds):
        if b is not None:
            continue
        prev = bounds[i - 1] if i > 0 else None
        left = prev[1] if prev is not None else float(hpos)
        nxt = next((bounds[j] for j in range(i + 1, len(bounds)) if bounds[j]), None)
        right = nxt[0] if nxt else float(hpos + width)
        bounds[i] = (left, max(left, right))

    # 3. monotonic, inside the box, every width >= 1
    return _repair(bounds, tokens, hpos, width)  # type: ignore[arg-type]


def _repair(
    bounds: list[tuple[float, float]],
    tokens: tuple[str, ...],
    hpos: int,
    width: int,
) -> tuple[WordBox, ...]:
    """Make the answer admissible, or the guard will drop it wholesale.

    A single overlapping pair would send the whole line back to the
    proportional fallback, which would score the resolver on lines it had
    in fact got right. Clamping here is not cosmetic: it is the difference
    between measuring the method and measuring its worst line.
    """
    n = len(tokens)
    right_edge = hpos + width
    # every token needs at least 1px, so nothing may start past this
    boxes: list[WordBox] = []
    cursor = hpos
    for i, span in enumerate(bounds):
        start, end = span
        remaining = n - i
        latest = right_edge - remaining
        x0 = int(max(cursor, min(round(start), latest)))
        # leave room for every token still to come
        latest_end = right_edge - (remaining - 1)
        x1 = int(max(x0 + 1, min(round(end), latest_end)))
        boxes.append(WordBox(text=tokens[i], hpos=x0, width=x1 - x0))
        cursor = x1
    return tuple(boxes)
