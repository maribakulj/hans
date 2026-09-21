"""Les boîtes au mot de Tesseract, recalées sur le texte corrigé.

Aucune géométrie n'est inventée ici. Tesseract segmente les mots depuis vingt
ans ; on prend ses boîtes et on les fait correspondre au texte qu'on doit
écrire, exactement comme on fait avec les découpes de kraken.

L'adaptateur est mince à dessein : les boîtes de mots deviennent des spans
par caractère, et tout le reste — appariement plié, interpolation des
caractères non ancrés, recoupage, invariants — est la machinerie déjà
éprouvée de :mod:`hans.cuts`. Une deuxième implémentation de l'alignement
serait une deuxième occasion de se tromper.
"""

from __future__ import annotations

import json
from pathlib import Path

from hans.cuts import LineCuts, support, transfer
from hans.geometry import GeometryRequest, WordBox
from hans.resolvers.proportional import ProportionalResolver


def _to_cuts(line_id: str, text: str, boxes: list[tuple[int, int]]) -> LineCuts:
    """Un span par caractère, réparti uniformément dans la boîte de son mot.

    Uniforme et non pondéré : à l'intérieur d'un mot, la position exacte d'un
    caractère n'intéresse personne — ce sont les FRONTIÈRES entre mots qui
    portent la géométrie, et celles-là viennent de Tesseract, pas d'ici.
    """
    words = text.split(" ")
    spans: list[tuple[int, int]] = []
    for i, (w, (a, b)) in enumerate(zip(words, boxes)):
        if i:
            spans.append((boxes[i - 1][1], a))  # l'espace
        n = max(1, len(w))
        step = (b - a) / n
        spans.extend((round(a + k * step), round(a + (k + 1) * step)) for k in range(n))
    return LineCuts(line_id=line_id, text=" ".join(words), spans=tuple(spans))


class TesseractWordsResolver:
    """Géométrie prise sur les mots que Tesseract a vus."""

    MIN_SUPPORT = 0.5

    def __init__(self, lines: dict[str, LineCuts], *, name: str | None = None):
        self._cuts = lines
        self.name = name or "tesseract (boites au mot)"
        self._fallback = ProportionalResolver()
        self.declined = 0

    @classmethod
    def from_cache(cls, path: Path | str, **kw: str) -> TesseractWordsResolver:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        out: dict[str, LineCuts] = {}
        for lid, entry in raw["lines"].items():
            boxes = [(int(a), int(b)) for a, b in entry["boxes"]]
            try:
                out[lid] = _to_cuts(lid, entry["text"], boxes)
            except ValueError:
                continue  # texte et boîtes désaccordés : la ligne est sautée
        return cls(out, **kw)

    def __len__(self) -> int:
        return len(self._cuts)

    def resolve(self, request: GeometryRequest) -> tuple[WordBox, ...]:
        read = self._cuts.get(request.line_id)
        if read is None:
            self.declined += 1
            return self._fallback.resolve(request)
        if support(read, "".join(request.tokens)) < self.MIN_SUPPORT:
            self.declined += 1
            return self._fallback.resolve(request)
        return transfer(read, request.tokens, request.hpos, request.width)
