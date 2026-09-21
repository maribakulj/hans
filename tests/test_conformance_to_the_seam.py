"""Les résolveurs de hans sont-ils branchables tels quels sur saknussemm ?

Les deux jeux de types portent les mêmes attributs — ``hpos``, ``width``,
``tokens``, ``line_id`` d'un côté ; ``text``, ``hpos``, ``width`` de l'autre —
donc le typage structurel devrait suffire, sans adaptateur. C'est le genre
d'affirmation qui se vérifie au lieu de se supposer : elle tiendrait jusqu'au
jour où l'un des deux renomme un champ, et rien ne le signalerait avant la
production.

Le test fait passer un résolveur de hans par le vrai ``_resolve_geometry``
de saknussemm, gardes comprises. Saute sans saknussemm, comme la parité.
"""

from __future__ import annotations

import pytest

from hans.cuts import LineCuts
from hans.resolvers import CTCCutsResolver, ProportionalResolver
from hans.resolvers.ctc import MissingLine

rewriter = pytest.importorskip(
    "saknussemm.formats.alto.rewriter",
    reason="saknussemm absent : installer l'extra [parity]",
)
schemas = pytest.importorskip("saknussemm.core.schemas")

TOKENS = ["de", " ", "la"]
HPOS, WIDTH = 100, 80


def _manifest():
    return schemas.LineManifest(
        line_id="L1",
        page_id="P1",
        block_id="TB1",
        line_order_global=0,
        line_order_in_block=0,
        coords=schemas.Coords(hpos=HPOS, vpos=10, width=WIDTH, height=40),
        ocr_text="dela",
    )


def _through_the_seam(resolver):
    """Le vrai chemin : gardes de saknussemm comprises."""
    return rewriter._resolve_geometry(
        resolver, _manifest(), HPOS, 10, WIDTH, 40, list(TOKENS), None
    )


def test_the_ctc_resolver_plugs_in_without_an_adapter() -> None:
    cuts = {
        "L1": LineCuts(
            "L1", "de la", ((100, 118), (118, 130), (130, 140), (140, 152), (152, 170))
        )
    }
    geo = _through_the_seam(CTCCutsResolver(cuts))
    assert [t for t, _, _ in geo] == TOKENS
    # la frontière vient bien des découpes, pas du proportionnel
    assert geo[1][1] == 130


def test_the_seam_refuses_an_answer_it_cannot_vouch_for() -> None:
    """Un résolveur hors contrat doit retomber sur la géométrie d'origine."""

    class _Bad:
        name = "bad"

        def resolve(self, request):
            from hans.geometry import WordBox

            return (WordBox("de", 100, 18),)  # un seul token sur trois

    assert _through_the_seam(_Bad()) == rewriter._compute_geometry(
        HPOS, WIDTH, list(TOKENS)
    )


def test_a_missing_line_falls_back_through_the_seam() -> None:
    """``MissingLine`` est une exception : la couture la rattrape."""
    with pytest.raises(MissingLine):
        CTCCutsResolver({}).resolve(
            __import__("hans.geometry", fromlist=["GeometryRequest"]).GeometryRequest(
                hpos=HPOS, width=WIDTH, tokens=tuple(TOKENS), line_id="L1"
            )
        )
    assert _through_the_seam(CTCCutsResolver({})) == rewriter._compute_geometry(
        HPOS, WIDTH, list(TOKENS)
    )


def test_the_proportional_resolver_round_trips_to_itself() -> None:
    """La copie de hans, passée par la couture, rend ce que saknussemm rend."""
    assert _through_the_seam(ProportionalResolver()) == rewriter._compute_geometry(
        HPOS, WIDTH, list(TOKENS)
    )
