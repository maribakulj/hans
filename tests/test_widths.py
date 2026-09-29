"""The pixel-blind width model: what it learns, and what it may not see."""

from __future__ import annotations

import pytest

from hans.alto import ReferenceLine
from hans.corrupt import line_case
from hans.geometry import GeometryRequest, WordBox
from hans.resolvers.proportional import compute_geometry
from hans.widths import LearnedWidthResolver, distribute, learn_widths


def _line(line_id: str, words: list[tuple[str, int, int]]) -> ReferenceLine:
    boxes = tuple(WordBox(text=t, hpos=h, width=w) for t, h, w in words)
    return ReferenceLine(
        line_id=line_id,
        hpos=boxes[0].hpos,
        vpos=0,
        width=boxes[-1].right - boxes[0].hpos,
        height=10,
        words=boxes,
    )


# A tiny typeface: i=4, m=12, a=8, space=6. Every word box is the exact sum.
_FONT = {"i": 4, "m": 12, "a": 8}


def _word(text: str, hpos: int) -> tuple[str, int, int]:
    return text, hpos, sum(_FONT[c] for c in text)


def _page() -> list[ReferenceLine]:
    texts = [
        # each parity half must identify i, m and a on its own: the
        # resolver never sees the half it answers for
        ["mi", "ami", "im"],
        ["aim", "mm", "i"],
        ["mm", "ii", "aa"],
        ["ma", "aa", "iam"],
    ]
    lines = []
    for n, row in enumerate(texts):
        cursor, words = 0, []
        for t in row:
            w = _word(t, cursor)
            words.append(w)
            cursor = w[1] + w[2] + 6
        lines.append(_line(f"L{n}", words))
    return lines


def test_learns_the_typeface_from_word_boxes_alone() -> None:
    model = learn_widths(_page())
    # exact up to the ridge, which is 1e-6 of the diagonal
    assert model.glyph("i") == pytest.approx(4, abs=1e-3)
    assert model.glyph("m") == pytest.approx(12, abs=1e-3)
    assert model.glyph("a") == pytest.approx(8, abs=1e-3)
    assert model.space == pytest.approx(6)
    # a glyph the page never showed gets the page's mean, not a crash
    assert model.glyph("z") == pytest.approx(model.unit)
    # folded: an accented or capital letter shares its base glyph
    assert model.glyph("Í") == model.glyph("i")


def test_relative_model_is_scale_free() -> None:
    small = learn_widths(_page())
    big = learn_widths(
        [
            ReferenceLine(
                line_id=ln.line_id,
                hpos=ln.hpos * 3,
                vpos=0,
                width=ln.width * 3,
                height=30,
                words=tuple(
                    WordBox(text=w.text, hpos=w.hpos * 3, width=w.width * 3)
                    for w in ln.words
                ),
            )
            for ln in _page()
        ]
    )
    assert small.relative() == pytest.approx(big.relative(), abs=1e-3)
    assert small.relative()["m"] / small.relative()["i"] == pytest.approx(3.0, abs=1e-3)


def test_distribute_with_baseline_weights_is_the_baseline() -> None:
    """Weights 1 per glyph / 0.6 per space must reproduce ``compute_geometry``.

    Then, and only then, a different score is a different WEIGHT and not a
    different rounding.
    """
    for hpos, width, tokens in [
        (100, 300, ("de", " ", "la", " ", "Republique")),
        (0, 3, ("a", " ", "b", " ", "c", " ", "d")),
        (7, 1, ("x", " ", "y")),
        (12, 240, ("l'", "Etat", " ", "c'est", " ", "moi")),
    ]:
        weights = [len(t) * (0.6 if t.isspace() else 1.0) for t in tokens]
        ours = [
            (b.text, b.hpos, b.width) for b in distribute(hpos, width, tokens, weights)
        ]
        assert ours == compute_geometry(hpos, width, list(tokens))


def test_resolver_recovers_the_boundary_the_baseline_misses() -> None:
    page = _page()
    # "mm" + "ii" : proportional cuts 24+6+8 = 38 px in half; the truth is 24 | 8
    case = line_case(page[2])
    assert case is not None
    resolver = LearnedWidthResolver(page)
    boxes = resolver.resolve(case.request())
    space = boxes[1]
    assert (space.hpos, space.right) == (24, 30)


def test_cross_fit_never_learns_from_the_line_it_resolves() -> None:
    """Rule 9: the page must carry the INPUT, never the answer.

    Poison one line with absurd boxes. The model used for THAT line must be
    unaffected (it was fitted on the other parity); the model used for its
    neighbours must have swallowed the poison. That is the only observable
    that proves the split is real.
    """
    page = _page()
    poisoned = _line("L1", [("iii", 0, 900), ("mmm", 950, 3)])
    page[1] = poisoned
    resolver = LearnedWidthResolver(page)
    own = resolver.model_for("L1")  # fitted on L0, L2 -- clean
    other = resolver.model_for("L0")  # fitted on L1, L3 -- poisoned
    assert own.token("iii") == pytest.approx(12, abs=1e-2)
    # the poison lands somewhere in the other model (on the per-word
    # constant, as it happens); what matters is that it landed THERE
    assert other.token("iii") > 100


def test_cross_fit_refuses_duplicate_line_ids() -> None:
    page = _page()
    page[1] = _line("L0", [("mi", 0, 16), ("am", 22, 20)])
    with pytest.raises(ValueError):
        LearnedWidthResolver(page)


def test_unknown_line_raises_rather_than_guessing() -> None:
    resolver = LearnedWidthResolver(_page())
    with pytest.raises(KeyError):
        resolver.resolve(
            GeometryRequest(hpos=0, width=50, tokens=("a", " ", "b"), line_id="nope")
        )
