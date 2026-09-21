"""Démo : la chaîne assemblée, du texte corrigé aux boîtes recalées.

    python tools/demo_pipeline.py <alto.xml> <cuts.json> <gaps.json> <sortie/>

Ce que ça montre, sur une vraie page : ce que la couture change. La MÊME
correction est projetée deux fois — une fois avec la géométrie de production
(répartition proportionnelle), une fois avec le résolveur CTC recalé sur
l'encre — et les deux ALTO sortent côte à côte.

Le reste de saknussemm ne bouge pas : mêmes gardes, mêmes chemins de
réécriture, même comptabilité des pertes. Seul le dessin des boîtes diffère,
et seulement sur les lignes dont la correction a changé le nombre de mots.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from saknussemm.formats.alto.rewriter import rewrite_alto_file  # noqa: E402
from saknussemm.formats.loader import build_document_manifest  # noqa: E402

from hans.resolvers import CTCCutsResolver, InkSnapResolver  # noqa: E402


def corrections_from(path: Path) -> dict[str, str]:
    """``{line_id: texte corrigé}`` depuis une sortie de campagne."""
    from lxml import etree

    out: dict[str, str] = {}
    for el in etree.parse(str(path)).iter():
        if not isinstance(el.tag, str):
            continue
        if etree.QName(el).localname != "TextLine":
            continue
        words = [
            c.get("CONTENT")
            for c in el
            if isinstance(c.tag, str)
            and etree.QName(c).localname == "String"
            and c.get("CONTENT")
        ]
        if el.get("ID") and words:
            out[el.get("ID")] = " ".join(words)
    return out


def main() -> int:
    alto, cuts, gaps, outdir = (Path(a) for a in sys.argv[1:5])
    corrected_alto = Path(sys.argv[5]) if len(sys.argv) > 5 else None
    outdir.mkdir(parents=True, exist_ok=True)

    manifest = build_document_manifest([(alto, alto.name)])
    pages = list(manifest.pages)
    nlines = sum(len(p.lines) for p in pages)

    if corrected_alto:
        fixed = corrections_from(corrected_alto)
        changed = 0
        for page in pages:
            for lm in page.lines:
                new = fixed.get(lm.line_id)
                if new and new != lm.ocr_text:
                    object.__setattr__(lm, "corrected_text", new)
                    changed += 1
        print(f"{nlines} lignes, {changed} corrigées", flush=True)
    else:
        print(f"{nlines} lignes, aucune correction fournie", flush=True)

    ctc = CTCCutsResolver.from_cache(cuts)
    resolver = InkSnapResolver.from_cache(
        CTCCutsResolver.from_cache(cuts), gaps, name="ctc + encre"
    )

    runs = {
        "production": None,          # géométrie proportionnelle, l'existant
        "ctc-encre": resolver,       # la couture, remplie
    }
    results = {}
    for label, geom in runs.items():
        res = rewrite_alto_file(
            alto, pages, "demo", "mistral-small-latest", word_geometry=geom
        )
        (outdir / f"alto-{label}.xml").write_bytes(res.xml_bytes)
        results[label] = res
        print(
            f"  {label:<12} -> alto-{label}.xml   "
            f"chemins: {dict(sorted(_count(res.rewriter_paths).items()))}",
            flush=True,
        )

    a, b = (results["production"].xml_bytes, results["ctc-encre"].xml_bytes)
    print(f"\nles deux ALTO diffèrent : {a != b}")

    # Ce qui a bougé, et de combien. Seules les lignes du chemin LENT peuvent
    # differer : ailleurs la boite d'origine est conservee telle quelle.
    from hans.alto import read_lines

    # Indexé par (ligne, RANG), jamais par le texte : une page porte cent
    # fois le mot « de », et les indexer par leur contenu compare des boîtes
    # de lignes différentes. Premier jet : « déplacement médian 1829 px »,
    # soit un tiers de page, ce qui aurait dû sauter aux yeux.
    P = {
        (ln.line_id, i): w
        for ln in read_lines(outdir / "alto-production.xml")
        for i, w in enumerate(ln.words)
    }
    moved, shifts = 0, []
    for ln in read_lines(outdir / "alto-ctc-encre.xml"):
        for i, w in enumerate(ln.words):
            other = P.get((ln.line_id, i))
            if other is None:
                continue
            d = abs(w.hpos - other.hpos) + abs(w.width - other.width)
            if d:
                moved += 1
                shifts.append(d)
    if shifts:
        shifts.sort()
        print(
            f"boîtes déplacées : {moved}   "
            f"déplacement médian {shifts[len(shifts) // 2]} px, max {shifts[-1]} px"
        )
    print(f"résolveur disponible sur {len(ctc)} lignes")
    (outdir / "resume.json").write_text(
        json.dumps(
            {"lignes": nlines, "identiques": a == b, "boites_deplacees": moved},
            ensure_ascii=False,
        )
    )
    return 0


def _count(paths: dict[str, str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in paths.values():
        out[v] = out.get(v, 0) + 1
    return out


if __name__ == "__main__":
    raise SystemExit(main())
