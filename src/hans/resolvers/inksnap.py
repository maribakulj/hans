"""Recoller les bords d'une boîte sur l'encre qu'elle est censée couvrir.

Le CTC est *peaky* : il allume un caractère à un instant plutôt que sur toute
sa largeur, donc la boîte d'un mot construite depuis ses découpes s'arrête un
peu avant l'encre. Mesuré le 2026-09-22 sur les fusions N→1 de la page BnF :
bord gauche **+6,5 px** trop à droite, bord droit **−25,8 px** trop à gauche.

J'avais d'abord attribué cet écart à une différence de convention — le
producteur gardant une marge que le CTC n'a pas. **C'était faux** : mesuré
sur 3 308 mots de ce producteur, sa marge médiane est de **0 px des deux
côtés**. Ses boîtes collent à l'encre elles aussi. L'écart était donc un
défaut du résolveur, pas un désaccord de style.

Ce enveloppeur s'applique à n'importe quel résolveur : il élargit chaque
boîte de mot jusqu'aux bords de la plage d'encre qui la contient, sans
jamais franchir un blanc inter-mots ni empiéter sur ses voisines.
"""

from __future__ import annotations

import json
from pathlib import Path

from hans.geometry import GeometryRequest, WordBox
from hans.resolvers.proportional import is_space_token


class InkSnapResolver:
    """Un résolveur, plus le recollage de ses bords sur l'encre."""

    def __init__(
        self,
        inner: object,
        gaps: dict[str, list[tuple[int, int]]],
        *,
        name: str | None = None,
    ):
        self._inner = inner
        self._gaps = gaps
        self.name = name or f"{getattr(inner, 'name', 'resolver')} + encre"
        self.snapped = 0

    @classmethod
    def from_cache(cls, inner: object, path: Path | str, **kw: str) -> InkSnapResolver:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            inner,
            {
                lid: [(int(a), int(b)) for a, b in spans]
                for lid, spans in raw["lines"].items()
            },
            **kw,
        )

    def resolve(self, request: GeometryRequest) -> tuple[WordBox, ...]:
        boxes = self._inner.resolve(request)  # type: ignore[attr-defined]
        gaps = self._gaps.get(request.line_id)
        if not gaps:
            return boxes  # type: ignore[no-any-return]

        left_limit = request.hpos
        right_limit = request.hpos + request.width
        out: list[WordBox] = []
        for i, b in enumerate(boxes):
            if is_space_token(b.text):
                out.append(b)
                continue
            # Les blancs qui encadrent ce mot bornent l'élargissement : on
            # étend jusqu'à l'encre, jamais jusque dans le mot d'à côté.
            before = max(
                (g[1] for g in gaps if g[1] <= b.hpos + b.width // 2),
                default=left_limit,
            )
            after = min(
                (g[0] for g in gaps if g[0] >= b.hpos + b.width // 2),
                default=right_limit,
            )
            lo = max(
                before, left_limit, out[-1].hpos + out[-1].width if out else left_limit
            )
            hi = min(after, right_limit)
            nh, nr = (
                min(b.hpos, max(lo, 0)),
                max(b.hpos + b.width, min(hi, right_limit)),
            )
            if nr - nh > 0 and (nh != b.hpos or nr != b.hpos + b.width):
                self.snapped += 1
                out.append(WordBox(b.text, int(nh), int(nr - nh)))
            else:
                out.append(b)
        return tuple(out)
