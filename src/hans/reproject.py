"""Remettre un texte corrigé sur ses lignes, au CARACTÈRE.

Le problème, mesuré : une correction de page entière donne le meilleur texte
(3,7 % d'écart à la vérité terrain contre 8,3 % en ne faisant rien), mais le
modèle ne rend pas toujours le bon nombre de lignes — 2 à 4 pages sur 9.

``core/page_alignment.align_page_lines`` de saknussemm sait retrouver quelle
ligne rendue répond à quelle ligne source, mais il compare par **jetons**
(Jaccard). Or une correction qui scinde un mot — ``Maisiepenfois`` devenant
``Mais ie penſois`` — ne partage **aucun jeton** avec sa source. Les lignes
qui profitent le plus de la correction sont donc exactement celles que
l'alignement refuse : **43 lignes sur 251 perdues**, et le gain retombe de
3,7 % à 6,4 %.

Au caractère, rien de tout ça : une scission ne change pas les lettres.
Mesuré sur les mêmes sorties, le gain est **intégralement conservé**.

Le choix du Jaccard n'était pas fautif — il a été validé sur une copie
*corrompue*, où les jetons survivent. Il l'est devenu face à une copie
*corrigée*, où ils ne survivent pas. Deux modes de panne, deux métriques.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

#: En dessous, la ligne rendue ne ressemble plus à sa source : le flux a
#: probablement été réordonné ou le texte remplacé, et la découpe ne
#: transporte plus rien de fiable. Heuristique, pas une mesure calibrée.
MIN_LINE_SIMILARITY = 0.5


@dataclass(frozen=True)
class Reprojection:
    """Le résultat d'une reprojection, avec ce qu'elle n'a pas su garantir.

    ``reproject_lines`` conserve le NOMBRE de lignes ; il ne conserve ni leur
    identité ni leur contenu. Contre-exemples exécutés (contre-revue du
    7/10/2026) : ``["abc", "def"]`` rendu ``["abc", "de", "f"]`` donne
    ``["abc", "de\nf"]`` ; deux lignes permutées donnent ``["", "l1\nl2"]``.
    L'API ne renvoyait aucun signal. Ici chaque anomalie est nommée par
    l'indice de la ligne source qu'elle touche, et ``ok`` dit si la sortie
    peut être prise comme « une ligne physique par ligne ».
    """

    lines: tuple[str, ...]
    #: lignes source non vides dont la sortie est vide
    emptied: tuple[int, ...]
    #: lignes dont la sortie contient encore un retour à la ligne
    merged: tuple[int, ...]
    #: lignes dont la sortie ressemble trop peu à la source
    dissimilar: tuple[int, ...]

    @property
    def ok(self) -> bool:
        return not (self.emptied or self.merged or self.dissimilar)

    @property
    def suspect(self) -> tuple[int, ...]:
        return tuple(
            sorted(set(self.emptied) | set(self.merged) | set(self.dissimilar))
        )


def reproject(source: list[str], returned: list[str]) -> Reprojection:
    """Comme :func:`reproject_lines`, en disant ce qui n'a pas tenu."""
    lines = reproject_lines(source, returned)
    emptied: list[int] = []
    merged: list[int] = []
    dissimilar: list[int] = []
    for i, (src, out) in enumerate(zip(source, lines)):
        if src.strip() and not out.strip():
            emptied.append(i)
            continue
        if "\n" in out:
            merged.append(i)
        if (
            src.strip()
            and SequenceMatcher(None, src, out, autojunk=False).ratio()
            < MIN_LINE_SIMILARITY
        ):
            dissimilar.append(i)
    return Reprojection(tuple(lines), tuple(emptied), tuple(merged), tuple(dissimilar))


def reproject_lines(source: list[str], returned: list[str]) -> list[str]:
    """Une ligne de sortie par ligne SOURCE, découpée dans le flux rendu.

    Les deux textes sont concaténés puis alignés caractère à caractère ; les
    frontières de lignes d'origine sont transportées par l'alignement, et le
    flux rendu est recoupé dessus. Le nombre de lignes rendu par le modèle
    n'a donc plus d'importance — ce qui compte est que le flux reste
    monotone. Un modèle qui réordonne N'EST PAS visible ici : cette fonction
    garantit le compte, pas l'identité des lignes. :func:`reproject` renvoie
    la même découpe avec les lignes vidées, fusionnées ou méconnaissables.
    """
    if not source:
        return []
    src_stream = "\n".join(source)
    tgt_stream = "\n".join(returned)

    marks: list[int] = []
    pos = 0
    for line in source[:-1]:
        pos += len(line) + 1
        marks.append(pos)

    mapped: dict[int, int] = {}
    for _tag, i1, i2, j1, j2 in SequenceMatcher(
        None, src_stream, tgt_stream, autojunk=False
    ).get_opcodes():
        for m in marks:
            if i1 <= m <= i2:
                mapped[m] = j1 + min(m - i1, j2 - j1)

    cuts = [0] + [mapped.get(m, m) for m in marks] + [len(tgt_stream)]
    # Monotonie : une frontière ne peut pas reculer sur la précédente.
    for i in range(1, len(cuts)):
        cuts[i] = max(cuts[i], cuts[i - 1])
    return [tgt_stream[cuts[i] : cuts[i + 1]].strip("\n") for i in range(len(source))]
