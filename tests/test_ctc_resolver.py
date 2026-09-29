"""The candidate's own contract: what it answers, and when it declines."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hans.cuts import LineCuts
from hans.geometry import GeometryRequest, WordBox
from hans.resolvers.ctc import CTCCutsResolver, MissingLine, WeightedCTCCutsResolver

TOKENS = ("de", " ", "la")


def _request(line_id: str = "L1") -> GeometryRequest:
    return GeometryRequest(hpos=100, width=80, tokens=TOKENS, line_id=line_id)


def _cache(text: str = "de la") -> dict[str, LineCuts]:
    spans = ((100, 118), (118, 130), (130, 140), (140, 152), (152, 170))
    return {"L1": LineCuts("L1", text, spans)}


def test_a_line_absent_from_the_cache_raises(tmp_path: Path) -> None:
    """Never a silent fallback: the bench counts a raise as a failure.

    A cache that quietly misses half a corpus must show up as a failure
    count, not as a score computed on the easy half.
    """
    with pytest.raises(MissingLine):
        CTCCutsResolver({}).resolve(_request())


def test_a_weak_reading_is_handed_back_to_the_incumbent() -> None:
    """What the seam does anyway, reproduced so the bench measures it.

    Scoring a refusal as a failure instead would let the candidate improve
    its worst case simply by declining every hard line.
    """
    resolver = CTCCutsResolver(_cache("zzzzz"))
    boxes = resolver.resolve(_request())
    assert resolver.declined == 1
    from hans.resolvers import ProportionalResolver

    assert boxes == ProportionalResolver().resolve(_request())


def test_a_strong_reading_is_used_and_counts_no_decline() -> None:
    resolver = CTCCutsResolver(_cache())
    boxes = resolver.resolve(_request())
    assert resolver.declined == 0
    assert (boxes[1].hpos, boxes[1].hpos + boxes[1].width) == (130, 140)


def test_the_fallback_is_injectable() -> None:
    """So a campaign can state which incumbent it is comparing against."""

    class _Marker:
        name = "marker"

        def resolve(self, request: GeometryRequest) -> tuple[WordBox, ...]:
            return (WordBox("sentinel", 0, 1),)

    resolver = CTCCutsResolver(_cache("zzzzz"), fallback=_Marker())
    assert resolver.resolve(_request())[0].text == "sentinel"


def test_from_cache_round_trips_a_written_file(tmp_path: Path) -> None:
    path = tmp_path / "cuts.json"
    path.write_text(
        json.dumps(
            {
                "lines": {
                    "L1": {
                        "text": "de la",
                        "spans": [
                            [100, 118],
                            [118, 130],
                            [130, 140],
                            [140, 152],
                            [152, 170],
                        ],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    resolver = CTCCutsResolver.from_cache(path)
    assert len(resolver) == 1
    assert resolver.resolve(_request())[0].text == "de"


def test_weighted_resolver_learns_from_its_cache() -> None:
    cuts = {
        "train": LineCuts("train", "W i", ((0, 20), (20, 24), (24, 29))),
        "L1": LineCuts(
            "L1",
            "a??ib",
            ((0, 10), (10, 20), (20, 30), (30, 35), (35, 45)),
        ),
    }
    request = GeometryRequest(
        hpos=0, width=45, tokens=("aW", " ", "ib"), line_id="L1"
    )
    plain = CTCCutsResolver(cuts).resolve(request)
    weighted = WeightedCTCCutsResolver(cuts).resolve(request)
    assert weighted[1].width < plain[1].width
    assert weighted[0].hpos == plain[0].hpos
    assert weighted[-1].hpos + weighted[-1].width == 45
