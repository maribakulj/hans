"""Le recollage sur l'encre : il élargit, sans jamais déplacer une frontière."""

from __future__ import annotations

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


def test_the_boundary_is_not_moved() -> None:
    """La propriété qui compte : élargir ne doit pas recouper ailleurs.

    Les frontières sont ce que le banc note ; si le recollage les déplaçait,
    il échangerait un gain d'étendue contre une perte de placement, et la
    mesure globale le cacherait derrière une IoU flatteuse.
    """
    before = _Tight().resolve(REQ)
    after = _snap().resolve(REQ)
    gap_before = next(b for b in before if is_space_token(b.text))
    gap_after = next(b for b in after if is_space_token(b.text))
    assert gap_before.hpos == gap_after.hpos
    assert gap_before.width == gap_after.width


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
