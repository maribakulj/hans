"""Whatever the resolver answers, saknussemm's guard must accept it.

``_geometry_is_usable`` drops an inadmissible answer wholesale and falls
back to the proportional geometry. A resolver that trips it on hard lines
would be scored on its easy ones here and silently disabled in production —
the two failures look nothing alike and neither announces itself.

Skips without saknussemm, like the baseline parity test, so CI stays
self-contained.
"""

from __future__ import annotations

import pytest

from hans.cuts import LineCuts, transfer

rewriter = pytest.importorskip(
    "saknussemm.formats.alto.rewriter",
    reason="saknussemm absent: install the [parity] extra",
)

CASES = [
    ("de la", ("de", " ", "la"), 100, 80),
    ("DE LA", ("de", " ", "la"), 100, 80),
    ("zzzzz", ("de", " ", "la"), 100, 80),
    ("", ("de", " ", "la"), 100, 80),
    ("de la", ("de", " ", "la"), 0, 5),
    ("a b c", ("a", " ", "b", " ", "c"), 0, 5),
    ("bie burd bie", ("die", " ", "durch", " ", "die"), 10, 400),
    ("de la", ("un", " ", "mot", " ", "de", " ", "plus"), 100, 80),
]


@pytest.mark.parametrize("read_text,tokens,hpos,width", CASES)
def test_the_seam_accepts_every_answer(
    read_text: str, tokens: tuple[str, ...], hpos: int, width: int
) -> None:
    read = LineCuts("L1", read_text, tuple((i, i + 1) for i in range(len(read_text))))
    boxes = transfer(read, tokens, hpos, width)
    token_boxes = tuple(
        rewriter.TokenBox(text=b.text, hpos=b.hpos, width=b.width) for b in boxes
    )
    assert rewriter._geometry_is_usable(token_boxes, list(tokens), hpos, width)
