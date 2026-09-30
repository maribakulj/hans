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

import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher
from statistics import median

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


def _fold(text: str) -> str:
    """Case- and accent-insensitive form, used ONLY to find the match.

    Positions always come from the original characters; this only decides
    which character corresponds to which. Measured on 2026-09-21: the
    heading ``Chronique Locale`` in the ALTO is read ``CHRONIQUE LOCALE`` by
    the model -- small capitals -- and a case-sensitive matcher anchors
    almost nothing on such a line, falls back to interpolating across its
    whole width, and puts a boundary 168 px out. The characters are the same
    characters; only their case differs, and case is not geometry.
    """
    return "".join(_fold_char(c) for c in text)


def _fold_char(char: str) -> str:
    """Exactly one character out for one character in.

    The invariant is load-bearing and it was learned the hard way: the
    matcher runs on the folded strings while the POSITIONS are indexed in
    the originals, so a fold that changes length silently shifts every
    position after it. Folding naively -- lower(), NFD, drop the combining
    marks over the whole string -- did exactly that, and dropped the
    candidate from 99.6% to 77.7% on a corpus it had got right. Nothing
    raised; the boxes just moved.
    """
    lowered = char.lower()
    base = "".join(
        c for c in unicodedata.normalize("NFD", lowered) if not unicodedata.combining(c)
    )
    return base[0] if base else char


def learn_char_widths(reads: Iterable[LineCuts]) -> dict[str, float]:
    """Learn relative glyph widths from the recogniser's own character cuts.

    **What a cut is, measured, not assumed.** On the BnF cache (538 lines,
    2026-09-29) 84 % of the per-character cuts have a width of ZERO pixels
    and every letter's median width is 0; only the space carries 4-5 px.
    A CTC recogniser emits each character as a spike in one frame, so
    ``rec.cuts`` holds where a glyph was *emitted*, not how wide it is.
    Learning from ``x1 - x0`` therefore learns nothing: the first version
    of this function produced 1.00 for every letter (``m`` = 0.75, ``h`` =
    1.17, noise) and moved 0 boundaries out of 13 385 on three corpora.

    What DOES carry the width is the advance from one spike to the next:
    on the same cache, ``i``/``l`` come out at 0.67 of the line's median
    advance, ``a``/``e`` at 1.1, ``m`` at 1.8, ``w`` at 1.9 -- the shape of
    a typeface. So each character is measured by the distance to the start
    of the next one, and the last character of a line by its own span
    (which is exact when spans are contiguous, and zero -- hence skipped --
    when they are spikes).

    Each line is normalised by its median positive advance before it
    contributes, which removes point size and scan scale. The model never
    predicts absolute pixels: interpolation already knows the exact width
    between its anchors, and these values only divide that width.
    """
    samples: dict[str, list[float]] = defaultdict(list)
    for read in reads:
        spans = read.spans
        advances = [
            max(0, spans[k + 1][0] - spans[k][0])
            if k + 1 < len(spans)
            else max(0, spans[k][1] - spans[k][0])
            for k in range(len(spans))
        ]
        positive = [a for a in advances if a > 0]
        if not positive:
            continue
        scale = float(median(positive))
        if scale <= 0:
            continue
        for char, advance in zip(read.text, advances):
            if advance <= 0:
                continue
            samples[_fold_char(char)].append(advance / scale)
    return {char: float(median(values)) for char, values in samples.items()}


def support(read: LineCuts, target: str) -> float:
    """Share of ``target`` the recogniser's reading can actually anchor.

    The pixel evidence for a transcription, reduced to one number. Where it
    is low, the model and the target are not describing the same ink -- a
    garbled source, a hallucinated correction, a heading the model missed --
    and geometry invented there would have nothing underneath it.
    """
    if not target:
        return 0.0
    blocks = SequenceMatcher(
        None, _fold(read.text), _fold(target), autojunk=False
    ).get_matching_blocks()
    return sum(size for _, _, size in blocks) / len(target)


def _char_positions(read: LineCuts, target: str) -> list[tuple[float, float] | None]:
    """One span per character of ``target``, or None where nothing matched.

    Matching is character-level between what was read and what must be
    written. The two differ for ordinary reasons -- the model resolves an
    apostrophe differently, the correction changed a word -- and the
    unmatched positions are filled in afterwards rather than guessed here.
    """
    out: list[tuple[float, float] | None] = [None] * len(target)
    matcher = SequenceMatcher(None, _fold(read.text), _fold(target), autojunk=False)
    for src, dst, size in matcher.get_matching_blocks():
        for k in range(size):
            x0, x1 = read.spans[src + k]
            out[dst + k] = (float(x0), float(x1))
    return out


def _fill_gaps(
    positions: list[tuple[float, float] | None],
    hpos: int,
    width: int,
    target: str,
    char_widths: Mapping[str, float] | None = None,
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
        count = j - i

        # Without a model this is exactly the old equal-step interpolation.
        # With a model, only the division INSIDE the anchored interval changes.
        weights = (
            [
                max(0.05, float(char_widths.get(_fold_char(target[k]), 1.0)))
                for k in range(i, j)
            ]
            if char_widths
            else [1.0] * count
        )
        total = sum(weights)
        cursor = start
        cumulative = 0.0
        for weight in weights:
            cumulative += weight
            nxt = start + (end - start) * cumulative / total
            filled.append((cursor, nxt))
            cursor = nxt
        i = j
    return filled


def transfer(
    read: LineCuts,
    tokens: tuple[str, ...],
    hpos: int,
    width: int,
    *,
    char_widths: Mapping[str, float] | None = None,
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
    positions = _fill_gaps(
        _char_positions(read, target), hpos, width, target, char_widths
    )

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
