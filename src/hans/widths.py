"""Relative glyph widths learned from a page's own word boxes. Pixel-blind.

The proportional baseline assumes every glyph is as wide as every other and
a space is 0.6 of one. That is the whole of its typographic knowledge, and
it is wrong in a way any page can measure: an ALTO already carries hundreds
of ``String`` elements with a ``CONTENT`` and a ``WIDTH``, and the width of
a word is, to a first approximation, the sum of the widths of its letters.
That is a small linear system -- one unknown per character, one equation
per word -- and it is solvable from the page alone, with no image, no model
and no dependency. It therefore stays inside saknussemm's ``I4`` (the core
never opens an image).

The solve is least squares in pure Python -- the bench has no numpy, and
the system is one unknown per distinct character, a hundred at most -- with
one round of outlier trimming so a mis-boxed heading or a column-wide box
cannot pull every letter of the alphabet with it.

What the model is NOT: absolute geometry. It only ever divides a width that
is already known between the tokens that must share it -- the line box for
the pixel-blind resolver, an anchored interval for the CTC gap filler.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import pairwise
from statistics import median

from hans.alto import ReferenceLine
from hans.cuts import _fold_char
from hans.geometry import GeometryRequest, WordBox
from hans.resolvers.proportional import is_space_token

#: Below this fraction of the page's mean glyph width a learned value is
#: treated as noise. Nothing on a printed page is a twentieth of a letter.
_FLOOR = 0.05


@dataclass(frozen=True)
class WidthModel:
    """Widths per folded character, in the coordinate unit of the page."""

    glyphs: Mapping[str, float]
    space: float
    unit: float  # mean glyph width; the value for characters never seen

    def glyph(self, char: str) -> float:
        return self.glyphs.get(_fold_char(char), self.unit)

    def token(self, token: str) -> float:
        if is_space_token(token):
            return len(token) * self.space
        return sum(self.glyph(c) for c in token)

    def relative(self) -> dict[str, float]:
        """The same model scaled so the median glyph is 1.0.

        This is the shape ``hans.cuts.transfer`` takes for ``char_widths``:
        only ratios matter inside an anchored gap, and expressing them
        against the median makes the space and every unseen glyph land on
        a sane default.
        """
        values = sorted(self.glyphs.values())
        scale = values[len(values) // 2] if values else self.unit
        if scale <= 0:
            scale = 1.0
        out = {c: w / scale for c, w in self.glyphs.items()}
        out[" "] = self.space / scale
        return out


def _solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting. Small dense systems only."""
    n = len(rhs)
    m = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[pivot] = m[pivot], m[col]
        p = m[col][col]
        if abs(p) < 1e-12:
            continue
        for r in range(n):
            if r == col:
                continue
            f = m[r][col] / p
            if f:
                for k in range(col, n + 1):
                    m[r][k] -= f * m[col][k]
    return [m[i][n] / m[i][i] if abs(m[i][i]) > 1e-12 else 0.0 for i in range(n)]


def _least_squares(
    chars: list[str], rows: list[tuple[dict[str, int], float]], unit: float
) -> dict[str, float]:
    """Ridge least squares of word width on character counts.

    The ridge is a whisper (1e-6 of the diagonal): it only keeps a character
    that occurs in a single word from making the system singular.
    """
    index = {c: i for i, c in enumerate(chars)}
    n = len(chars)
    ata = [[0.0] * n for _ in range(n)]
    atb = [0.0] * n
    for counts, width in rows:
        items = [(index[c], k) for c, k in counts.items()]
        for i, ki in items:
            atb[i] += ki * width
            for j, kj in items:
                ata[i][j] += ki * kj
    ridge = 1e-6 * max(1.0, sum(ata[i][i] for i in range(n)) / max(1, n))
    for i in range(n):
        ata[i][i] += ridge
        atb[i] += ridge * unit  # shrink an unseen-ish glyph toward the mean
    beta = _solve(ata, atb)
    return dict(zip(chars, beta))


def learn_widths(lines: Iterable[ReferenceLine]) -> WidthModel:
    """Fit one width per character to the word boxes of ``lines``.

    Least squares of ``WIDTH`` on character counts, in two passes: the
    first fit finds the words whose box does not add up (a heading in a
    larger corps, a box that swallowed the column, a ``String`` that is not
    a word), the second fit leaves them out. Trimming is by median absolute
    deviation, three sigmas, so a page where everything adds up drops
    nothing and a page with a broken table drops the table.

    The space is learned from the blank between consecutive word boxes on
    the same line, which is the only place a page shows its width.
    """
    rows: list[tuple[dict[str, int], float]] = []
    gaps: list[float] = []
    for line in lines:
        for word in line.words:
            counts: dict[str, int] = defaultdict(int)
            for c in word.text:
                counts[_fold_char(c)] += 1
            if counts:
                rows.append((dict(counts), float(word.width)))
        for a, b in pairwise(line.words):
            gaps.append(float(b.hpos - a.right))

    total_chars = sum(sum(c.values()) for c, _ in rows)
    if total_chars == 0:
        return WidthModel(glyphs={}, space=0.6, unit=1.0)
    unit = sum(w for _, w in rows) / total_chars
    floor = _FLOOR * unit

    chars = sorted({c for counts, _ in rows for c in counts})
    beta = _least_squares(chars, rows, unit)

    residuals = [w - sum(k * beta[c] for c, k in counts.items()) for counts, w in rows]
    centre = median(residuals)
    mad = median(abs(r - centre) for r in residuals)
    # ALTO is integer-valued: nothing under a pixel is an outlier, and on a
    # page where every box adds up (MAD ~ 0) nothing must be trimmed at all.
    cut = max(3 * 1.4826 * mad, 1.0)
    keep = [row for row, r in zip(rows, residuals) if abs(r - centre) <= cut]
    if len(keep) < len(rows) and len(keep) >= len(chars):
        kept_chars = sorted({c for counts, _ in keep for c in counts})
        beta.update(_least_squares(kept_chars, keep, unit))

    glyphs = {c: max(floor, v) for c, v in beta.items()}
    space = max(floor, median(gaps)) if gaps else 0.6 * unit
    return WidthModel(glyphs=glyphs, space=space, unit=unit)


def distribute(
    hpos: int, width: int, tokens: tuple[str, ...], weights: list[float]
) -> tuple[WordBox, ...]:
    """Share ``width`` between ``tokens`` in proportion to ``weights``.

    Same arithmetic as the baseline -- each boundary rounded from one exact
    division, the min-1 floor repaid by the widest tokens -- so the only
    thing that differs between this and ``compute_geometry`` is the weight
    each token carries. That is the variable under test, and nothing else
    may move with it.
    """
    if not tokens:
        return ()
    total = sum(weights)
    if total <= 0:
        per = width // len(tokens)
        return tuple(
            WordBox(text=t, hpos=hpos + i * per, width=per)
            for i, t in enumerate(tokens)
        )

    widths: list[int] = []
    cumulative = 0.0
    prev = 0
    for w in weights:
        cumulative += w
        rounded = round(width * cumulative / total)
        widths.append(rounded - prev)
        prev = rounded

    if min(widths) < 1:
        deficit = 0
        for i, w in enumerate(widths):
            if w < 1:
                deficit += 1 - w
                widths[i] = 1
        while deficit > 0:
            donor = max(range(len(widths)), key=lambda i: widths[i])
            if widths[donor] <= 1:
                break
            take = min(deficit, widths[donor] - 1)
            widths[donor] -= take
            deficit -= take

    out: list[WordBox] = []
    cursor = hpos
    for t, w in zip(tokens, widths):
        out.append(WordBox(text=t, hpos=cursor, width=w))
        cursor += w
    return tuple(out)


class LearnedWidthResolver:
    """The proportional resolver, with the page's own letter widths.

    Pixel-blind like the baseline; the only extra input is the ALTO the
    line came from. Built from the lines of ONE page and answering for
    those lines.

    **Cross-fitting, and why it is not optional.** On the bench, the boxes
    a resolver is asked to recover are the very boxes this model would be
    learned from: fit it on the whole page and the answer leaks into the
    question (AUTOPILOT decision 3, rule 9 -- "le corpus porte-t-il l'ENTRÉE
    ou la réponse ?"). So the page is split by line parity and every line is
    resolved with the model fitted on the OTHER half. Each model sees half
    the evidence, which can only make the candidate look worse, never
    better. In production the same split is unnecessary: the destroyed
    boxes are gone and the rest of the page is legitimately available.
    """

    name = "learned widths (alto, cross-fit)"

    def __init__(self, lines: list[ReferenceLine]):
        ids = [ln.line_id for ln in lines]
        if len(set(ids)) != len(ids):
            raise ValueError("line IDs must be unique within a page to cross-fit")
        self._parity = {ln.line_id: i % 2 for i, ln in enumerate(lines)}
        # model[p] is fitted on the lines whose parity is NOT p
        self._models = (
            learn_widths([ln for i, ln in enumerate(lines) if i % 2 == 1]),
            learn_widths([ln for i, ln in enumerate(lines) if i % 2 == 0]),
        )

    def model_for(self, line_id: str) -> WidthModel:
        try:
            return self._models[self._parity[line_id]]
        except KeyError:
            raise KeyError(f"line {line_id!r} is not on the page this was fitted to")

    def resolve(self, request: GeometryRequest) -> tuple[WordBox, ...]:
        model = self.model_for(request.line_id)
        weights = [model.token(t) for t in request.tokens]
        return distribute(request.hpos, request.width, request.tokens, weights)
