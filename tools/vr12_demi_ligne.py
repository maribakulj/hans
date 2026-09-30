"""VR-12 : une demi-ligne inventée se voit-elle, sans vérité terrain, aux mots ?

    .venv/bin/python tools/vr12_demi_ligne.py [motif]

La question posée par H19 et inscrite au plan de saknussemm : le plancher de
ressemblance compare la ligne entière, donc une correction dont une moitié
est inventée et l'autre juste passe (cas *Regards* D4 line_19). Peut-on
l'arrêter en comptant, mot par mot, ce qui n'a aucun appui dans la source
de la ligne ? La réserve était écrite d'avance : une ligne OCR en bouillie
corrigée JUSTE a, elle aussi, beaucoup de mots sans appui. « S'il n'y a pas
de seuil qui sépare, il n'y a pas de garde. »

Matière : les 29 runs de la campagne H20 (`~/corpus-vt/resultats/campagne/`),
qui gardent pour chaque ligne jugeable [source, sortie, VT].

Définitions :

- un mot de la sortie est **ancré** dans un texte quand, la sortie posée
  contre ce texte DANS L'ORDRE, au moins la moitié de ses lettres tombent
  dans une plage commune de trois caractères ou plus. C'est la fonction
  ``saknussemm.core.guards.unanchored_run`` (le test ci-dessous vérifie
  que ce fichier et elle comptent pareil). Les mots d'une ou deux lettres
  ne comptent ni ne coupent ;
- un mot **inventé** n'est ancré ni dans la source ni dans la VT ;
- une correction est **fautive** quand elle porte au moins trois mots
  inventés consécutifs : la « demi-ligne » de H19 ;
- le garde ne voit que source et sortie : la plus longue suite de mots
  consécutifs non ancrés dans la SOURCE.

Tout est compté en corrections **distinctes** (page, ligne, texte rendu) :
les 29 runs corrigent les mêmes pages, et la même sortie rendue par quatre
bras n'est pas quatre observations.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

RES = Path.home() / "corpus-vt" / "resultats" / "campagne"
_WORD = re.compile(r"[^\W\d_]+")
MIN_STRETCH = 3


def anchored(ref: str, out: str) -> list[bool]:
    """Pour chaque mot de plus de deux lettres de ``out`` : ancré dans ``ref`` ?"""
    a, b = ref.casefold(), out.casefold()
    hit = [False] * len(b)
    for blk in SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        if blk.size >= MIN_STRETCH:
            for k in range(blk.b, blk.b + blk.size):
                hit[k] = True
    return [
        2 * sum(hit[m.start() : m.end()]) >= m.end() - m.start()
        for m in _WORD.finditer(b)
        if m.end() - m.start() > 2
    ]


def longest(flags: list[bool]) -> int:
    best = cur = 0
    for f in flags:
        cur = cur + 1 if f else 0
        best = max(best, cur)
    return best


def lev(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def load(pattern: str) -> tuple[list[dict], dict[str, tuple[int, int]]]:
    rows: list[dict] = []
    totals: dict[str, list[int]] = {}
    for path in sorted(RES.glob("*.json")):
        if (
            path.name.startswith(("undeliverable", "sak_run"))
            or pattern not in path.name
        ):
            continue
        run = json.loads(path.read_text())
        if "corpus" not in run:
            continue
        tot = totals.setdefault(run["corpus"], [0, 0])
        for page, data in run.get("pages", {}).items():
            for lid, entry in (data.get("texts") or {}).items():
                src, out, vt = entry[0], entry[1], entry[2]
                e_src = lev(src, vt)
                tot[1] += len(vt)
                if out == src:
                    tot[0] += e_src
                    continue
                e_out = lev(out, vt)
                tot[0] += e_out
                rows.append(
                    {
                        "corpus": run["corpus"],
                        "producer": run["producer"],
                        "key": (page, lid, out),
                        "src": src,
                        "out": out,
                        "vt": vt,
                        "e_src": e_src,
                        "e_out": e_out,
                    }
                )
    return rows, {k: (v[0], v[1]) for k, v in totals.items()}


def annotate(rows: list[dict]) -> None:
    try:
        from saknussemm.core.guards import unanchored_run
    except ImportError:
        unanchored_run = None  # type: ignore[assignment]
    cache: dict[tuple, tuple[int, int]] = {}
    for r in rows:
        if r["key"] not in cache:
            in_src = anchored(r["src"], r["out"])
            in_vt = anchored(r["vt"], r["out"])
            run = longest([not x for x in in_src])
            if unanchored_run is not None:
                assert run == unanchored_run(r["src"], r["out"]), r["key"]
            cache[r["key"]] = (
                run,
                longest([not s and not v for s, v in zip(in_src, in_vt)]),
            )
        r["run"], r["inv"] = cache[r["key"]]


def report(corpus: str, rows: list[dict], e_out: int, total_l: int) -> None:
    distinct = {r["key"]: r for r in rows}
    faulty = {k for k, r in distinct.items() if r["inv"] >= 3}
    better = sum(1 for r in rows if r["e_out"] < r["e_src"])
    print(
        f"\n## {corpus} — {len(rows)} lignes changées sur les runs ({better} améliorées), "
        f"{len(distinct)} corrections distinctes, CER de sortie {e_out / total_l:.2%}"
    )
    print(
        f"corrections fautives (≥ 3 mots consécutifs ancrés ni dans la source ni dans la VT) : "
        f"**{len(faulty)}**, soit {len(faulty) / max(1, len(distinct)):.2%} des corrections distinctes"
    )
    print(
        "\n| garde | lignes arrêtées (tous runs) | corrections distinctes | dont fautives | "
        "dont justes (meilleures que la source) | CER si rendues à la source |"
    )
    print("|---|---|---|---|---|---|")
    for limit in (2, 3, 4):
        hit = [r for r in rows if r["run"] > limit]
        d = {r["key"]: r for r in hit}
        good = sum(1 for r in d.values() if r["e_out"] < r["e_src"])
        e_new = e_out + sum(r["e_src"] - r["e_out"] for r in hit)
        print(
            f"| suite > {limit} | {len(hit)} | {len(d)} | {len(set(d) & faulty)} | {good} | "
            f"{e_new / total_l:.2%} |"
        )
    stopped = {k: r for k, r in distinct.items() if r["run"] > 2}
    print(
        "\narrêtées à « suite > 2 », par producteur :",
        dict(Counter(r["producer"] for r in stopped.values()).most_common()),
    )
    print("\nFautives arrêtées (les plus longues suites) :")
    for r in sorted(
        (r for k, r in stopped.items() if k in faulty), key=lambda r: -r["run"]
    )[:6]:
        print(
            f"  [{r['producer']}] suite={r['run']}, erreurs {r['e_src']} → {r['e_out']}"
        )
        print(
            f"     source : {r['src'][:105]}\n     sortie : {r['out'][:105]}\n     VT     : {r['vt'][:105]}"
        )
    print("\nJustes arrêtées — le prix du garde :")
    for r in sorted(
        (r for k, r in stopped.items() if k not in faulty and r["e_out"] < r["e_src"]),
        key=lambda r: r["e_out"] - r["e_src"],
    )[:6]:
        print(
            f"  [{r['producer']}] suite={r['run']}, erreurs {r['e_src']} → {r['e_out']}"
        )
        print(
            f"     source : {r['src'][:105]}\n     sortie : {r['out'][:105]}\n     VT     : {r['vt'][:105]}"
        )


def main() -> int:
    pattern = sys.argv[1] if len(sys.argv) > 1 else ""
    rows, totals = load(pattern)
    annotate(rows)
    for corpus, (e_out, total_l) in totals.items():
        report(corpus, [r for r in rows if r["corpus"] == corpus], e_out, total_l)
    e_out = sum(v[0] for v in totals.values())
    total_l = sum(v[1] for v in totals.values())
    report("les deux corpus", rows, e_out, total_l)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
