"""Faire glisser les frontières du proportionnel jusqu'aux vrais blancs.

Pas de modèle, pas de réseau : un blanc entre deux mots est une colonne de
pixels sans encre, et un profil de projection verticale le donne directement.
C'est la méthode de l'OCR d'avant les réseaux, et elle mesure ce qu'on
cherche au lieu de l'inférer.

**Elle part du proportionnel et ne peut donc pas faire pire que lui** sur les
lignes où aucun blanc plausible n'existe : faute de candidat dans la
tolérance, la frontière proposée par ``_compute_geometry`` est conservée
telle quelle. C'est la différence avec un résolveur qui reconstruit tout —
celui-ci ne corrige que ce qu'il voit.
"""

from __future__ import annotations

import json
from pathlib import Path

from hans.geometry import GeometryRequest, WordBox
from hans.resolvers.proportional import ProportionalResolver, is_space_token


class InkGapResolver:
    """Géométrie proportionnelle, recalée sur les creux d'encre mesurés."""

    #: Au-delà de cette distance, en largeurs de caractère, un blanc n'est
    #: plus « le blanc de cette frontière » mais un autre blanc de la ligne.
    #: Y glisser quand même déplacerait un mot entier.
    TOLERANCE_CHARS = 1.5

    def __init__(
        self, gaps: dict[str, list[tuple[int, int]]], *, name: str | None = None
    ):
        self._gaps = gaps
        self.name = name or "ink gaps (sans modele)"
        self._base = ProportionalResolver()
        self.snapped = 0
        self.kept = 0

    @classmethod
    def from_cache(cls, path: Path | str, **kw: str) -> InkGapResolver:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            {
                lid: [(int(a), int(b)) for a, b in spans]
                for lid, spans in raw["lines"].items()
            },
            **kw,
        )

    def __len__(self) -> int:
        return len(self._gaps)

    def resolve(self, request: GeometryRequest) -> tuple[WordBox, ...]:
        base = self._base.resolve(request)
        gaps = self._gaps.get(request.line_id)
        if not gaps:
            return base

        chars = sum(len(t) for t in request.tokens) or 1
        tol = (request.width / chars) * self.TOLERANCE_CHARS

        # Une frontière par token d'espace, prise au milieu de sa boîte.
        targets = [
            (i, (b.hpos + b.hpos + b.width) / 2)
            for i, b in enumerate(base)
            if is_space_token(b.text)
        ]
        chosen = _assign(targets, gaps, tol, request.hpos)
        self.snapped += len(chosen)
        self.kept += len(targets) - len(chosen)

        if not chosen:
            return base
        return self._rebuild(base, chosen, request)

    @staticmethod
    def _rebuild(
        base: tuple[WordBox, ...],
        chosen: dict[int, tuple[int, int]],
        request: GeometryRequest,
    ) -> tuple[WordBox, ...]:
        """Redessiner les mots entre les frontières retenues.

        Les boîtes non contraintes gardent leur part proportionnelle du
        segment qui leur reste : on ne corrige que ce que l'encre a montré.
        """
        edges: list[float] = [float(request.hpos)]
        for i in range(len(base)):
            if i in chosen:
                edges.append(float(chosen[i][0]))
                edges.append(float(chosen[i][1]))
        edges.append(float(request.hpos + request.width))

        out: list[WordBox] = []
        seg_start = 0
        e = 0
        for i, box in enumerate(base):
            if i in chosen:
                a, b = chosen[i]
                # les tokens de seg_start..i-1 se partagent [edges[e], a]
                out.extend(_spread(base[seg_start:i], edges[e], a))
                out.append(WordBox(box.text, int(a), max(1, int(b - a))))
                e += 2
                seg_start = i + 1
        out.extend(_spread(base[seg_start:], edges[e], edges[-1]))
        return tuple(out)


def _assign(
    targets: list[tuple[int, float]],
    gaps: list[tuple[int, int]],
    tol: float,
    origin: int,
) -> dict[int, tuple[int, int]]:
    """Affecter k frontières à k blancs, en une passe globale et monotone.

    Le glouton « le blanc le plus proche » se fait piéger par la typographie
    serrée : il s'accroche au blanc inter-lettres voisin et déplace un mot
    entier. Mesuré : 91,1 % contre 84,4 % pour le proportionnel, alors que le
    nombre de frontières est CONNU et que les vrais blancs inter-mots sont
    les plus LARGES de la ligne.

    Le coût pèse donc les deux : l'écart à la position attendue, et la
    largeur du blanc rapportée à la plus grande de la ligne. Programmation
    dynamique sur les affectations croissantes — il y a au plus quelques
    dizaines de blancs par ligne.
    """
    if not targets or not gaps:
        return {}
    widest = max(b - a for a, b in gaps) or 1

    def cost(t: int, g: int) -> float:
        a, b = gaps[g]
        d = abs((a + b) / 2 - targets[t][1])
        if d > tol:
            return float("inf")
        return d / tol - 0.75 * ((b - a) / widest)

    n, m = len(targets), len(gaps)
    INF = float("inf")
    # best[t][g] = coût minimal pour placer les t premières frontières en
    # n'utilisant que les blancs < g
    best = [[INF] * (m + 1) for _ in range(n + 1)]
    back = [[-1] * (m + 1) for _ in range(n + 1)]
    for g in range(m + 1):
        best[0][g] = 0.0
    for t in range(1, n + 1):
        for g in range(1, m + 1):
            skip = best[t][g - 1]
            take = best[t - 1][g - 1] + cost(t - 1, g - 1)
            if take < skip:
                best[t][g] = take
                back[t][g] = g - 1
            else:
                best[t][g] = skip
                back[t][g] = -1
    if best[n][m] == INF:
        return {}
    out: dict[int, tuple[int, int]] = {}
    t, g = n, m
    cursor_ok = True
    while t > 0 and g > 0:
        if back[t][g] >= 0:
            gi = back[t][g]
            a, b = gaps[gi]
            out[targets[t - 1][0]] = (max(a, origin), b)
            t -= 1
            g = gi
        else:
            g -= 1
    return out if cursor_ok else {}


def _spread(boxes: tuple[WordBox, ...], left: float, right: float) -> list[WordBox]:
    """Répartir des tokens sur un segment, au prorata de leur largeur d'origine."""
    if not boxes:
        return []
    span = max(float(len(boxes)), right - left)
    total = sum(b.width for b in boxes) or 1
    out: list[WordBox] = []
    cursor = left
    for k, b in enumerate(boxes):
        w = span * b.width / total
        if k == len(boxes) - 1:
            w = max(1.0, left + span - cursor)
        out.append(WordBox(b.text, int(cursor), max(1, int(w))))
        cursor += w
    return out
