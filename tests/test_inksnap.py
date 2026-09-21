"""Le recollage sur l'encre : il élargit, sans jamais déplacer une frontière."""

from __future__ import annotations

import pytest

from hans.geometry import GeometryRequest, WordBox
from hans.resolvers import InkSnapResolver
from hans.resolvers.proportional import is_space_token

TOKENS = ("de", " ", "la")
REQ = GeometryRequest(hpos=100, width=80, tokens=TOKENS, line_id="L1")
# un seul blanc mesuré, entre les deux mots
GAPS = {"L1": [(130, 140)]}


class _Tight:
    """Rend des boîtes trop courtes, comme le fait un CTC peaky."""

    name = "tight"

    def resolve(self, request: GeometryRequest) -> tuple[WordBox, ...]:
        return (
            WordBox("de", 110, 10),  # l'encre va de 100 a 130
            WordBox(" ", 130, 10),
            WordBox("la", 150, 10),  # l'encre va de 140 a 180
        )


def _snap(gaps=GAPS):
    return InkSnapResolver(_Tight(), gaps)


def test_the_boxes_reach_the_ink() -> None:
    boxes = _snap().resolve(REQ)
    assert (boxes[0].hpos, boxes[0].hpos + boxes[0].width) == (100, 130)
    assert (boxes[2].hpos, boxes[2].hpos + boxes[2].width) == (140, 180)


def test_the_space_still_separates_the_words_it_sits_between() -> None:
    """Élargir un mot OBLIGE à redessiner le blanc qui le suit.

    J'avais d'abord écrit ici que la frontière ne devait pas bouger. C'est
    faux, et la fixture était trop simple pour le montrer : élargir un mot
    déplace nécessairement le début du blanc suivant. Ce qui doit tenir est
    plus faible et plus vrai — le blanc reste EXACTEMENT entre les deux mots
    qu'il sépare, sans les chevaucher.

    Mesuré sur la vraie page : les frontières passent de 99,8 % à 99,1 % de
    justesse, contre 19 points d'IoU gagnés. L'échange est réel et se dit.
    """
    boxes = _snap().resolve(REQ)
    for left, space, right in zip(boxes, boxes[1:], boxes[2:]):
        if not is_space_token(space.text):
            continue
        assert space.hpos == left.hpos + left.width
        assert space.hpos + space.width == right.hpos


def test_the_answer_survives_saknussemms_guard() -> None:
    """Le bug qui a coûté le plus cher : 9 réponses acceptées sur 200.

    Élargir les mots sans redessiner les blancs produit des boîtes qui se
    chevauchent. ``_geometry_is_usable`` rejette alors la ligne entière, qui
    retombe sur la géométrie proportionnelle — donc l'IoU mesurée décrivait
    une sortie que la production n'écrivait jamais.
    """
    rewriter = pytest.importorskip(
        "saknussemm.formats.alto.rewriter",
        reason="saknussemm absent : installer l'extra [parity]",
    )
    protocols = pytest.importorskip("saknussemm.core.protocols")

    boxes = _snap().resolve(REQ)
    tb = tuple(
        protocols.TokenBox(text=b.text, hpos=b.hpos, width=b.width) for b in boxes
    )
    assert rewriter._geometry_is_usable(tb, list(TOKENS), REQ.hpos, REQ.width)


def test_a_word_never_swallows_its_neighbour() -> None:
    """Sans blanc mesuré entre eux, deux mots ne doivent pas se recouvrir."""
    boxes = _snap({"L1": []}).resolve(REQ)
    assert boxes == _Tight().resolve(REQ)  # aucun blanc : on ne touche à rien


def test_boxes_stay_inside_the_line() -> None:
    boxes = _snap({"L1": [(95, 99), (130, 140), (181, 190)]}).resolve(REQ)
    assert boxes[0].hpos >= REQ.hpos
    assert boxes[-1].hpos + boxes[-1].width <= REQ.hpos + REQ.width


def test_a_line_absent_from_the_cache_is_passed_through() -> None:
    other = GeometryRequest(hpos=100, width=80, tokens=TOKENS, line_id="ABSENT")
    assert _snap().resolve(other) == _Tight().resolve(other)
