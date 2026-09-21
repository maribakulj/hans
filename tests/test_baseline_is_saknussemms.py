"""The copy must BE the original, or the comparison proves nothing.

``hans.resolvers.proportional.compute_geometry`` is a copy of saknussemm's
private ``_compute_geometry``. A copy that drifts turns the bench into a
comparison against a strawman that nobody ships -- the most flattering
possible error, and one no amount of downstream care would catch.

This test pins them together on a battery of inputs. It SKIPS where
saknussemm is not installed, which is how the bench stays runnable in a CI
with no access to an unpublished package.

Hence the AUTOPILOT rule: **a measurement taken in an environment where this
test skipped is not a measurement.** ``bench --strict`` refuses to run
there.
"""

from __future__ import annotations

import pytest

from hans.resolvers.proportional import compute_geometry, is_space_token

saknussemm_rewriter = pytest.importorskip(
    "saknussemm.formats.alto.rewriter",
    reason="saknussemm absent: install the [parity] extra to pin the copy",
)

CASES: list[tuple[int, int, list[str]]] = [
    (100, 300, ["de", " ", "la", " ", "Republique"]),
    (0, 100, ["hello"]),
    (50, 500, ["a", " ", "bb", " ", "ccc", " ", "dddd"]),
    (0, 3, ["a", " ", "b", " ", "c", " ", "d"]),  # min-1 floor territory
    (7, 1, ["x", " ", "y"]),  # width smaller than the token count
    (0, 1000, [" ", "mot", " "]),
    (12, 240, ["l'", "Etat", " ", "c'est", " ", "moi"]),
    (0, 0, ["a", " ", "b"]),
    (5, 77, []),
    (0, 50, [" ", " ", "x"]),  # no-break space is NOT a separator
]


@pytest.mark.parametrize("hpos,width,tokens", CASES)
def test_geometry_matches_saknussemm(hpos: int, width: int, tokens: list[str]) -> None:
    assert compute_geometry(hpos, width, tokens) == (
        saknussemm_rewriter._compute_geometry(hpos, width, list(tokens))
    )


@pytest.mark.parametrize("token", [" ", "  ", "\t", "\n", " ", " ", " ", "x", "", " x"])
def test_space_predicate_matches_saknussemm(token: str) -> None:
    """The no-break spaces are the whole point of this one.

    Treating U+00A0 as a separator would route it through an SP element,
    which carries no content -- replacing the character with an ordinary
    space and destroying the only thing it was there to say.
    """
    assert is_space_token(token) == saknussemm_rewriter._is_space_token(token)
