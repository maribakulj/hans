"""Inventions : un mot retiré de l'ALTO, remis par la correction — où le rewriter le pose-t-il ?

    .venv/bin/python tools/insertions.py

La vérité est mécanique, comme pour les fusions : la boîte du mot retiré est
celle du producteur, personne ne l'a choisie. Une ligne sur quatre, un mot
par ligne, trois positions (au milieu, en tête, en fin de ligne). On mesure
les deux bords du mot remis, en caractères, à travers le vrai
rewrite_alto_file de saknussemm (PR #167).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
from campagne_locale import _local
from lxml import etree
from saknussemm.formats.loader import adapter_for_format, build_document_manifest

from hans.alto import read_lines


def drop_in_tree(root, line_id, i):
    for el in root.iter():
        if _local(el) != "TextLine" or el.get("ID") != line_id:
            continue
        strings = [c for c in el if _local(c) == "String"]
        w = strings[i]
        # the SP after it (or before it, at the line end) goes with it
        sib = w.getnext()
        if sib is not None and _local(sib) == "SP":
            el.remove(sib)
        elif (prev := w.getprevious()) is not None and _local(prev) == "SP":
            el.remove(prev)
        el.remove(w)
        return True
    return False


def run(name, files, position):
    errs_l, errs_r, n = [], [], 0
    for path in files:
        lines = read_lines(path)
        truth = {l.line_id: l for l in lines}
        ids = [l.line_id for l in lines]
        if len(set(ids)) != len(ids):
            continue
        chosen = {}
        for k, l in enumerate(lines):
            if k % 4 or len(l.words) < 3:
                continue
            i = {"intérieur": len(l.words) // 2, "début": 0, "fin": len(l.words) - 1}[
                position
            ]
            chosen[l.line_id] = i
        tree = etree.parse(str(path))
        root = tree.getroot()
        for lid, i in list(chosen.items()):
            if not drop_in_tree(root, lid, i):
                del chosen[lid]
        tmp = ROOT / ".ins_tmp.xml"
        tree.write(str(tmp), xml_declaration=True, encoding=tree.docinfo.encoding)
        try:
            doc = build_document_manifest([(tmp, tmp.name)])
            for page in doc.pages:
                for lm in page.lines:
                    if lm.line_id in chosen:
                        words = [w.text for w in truth[lm.line_id].words]
                        i = chosen[lm.line_id]
                        # remettre le mot dans le texte OCR reconstruit
                        toks = lm.ocr_text.split(" ")
                        lm.corrected_text = (
                            " ".join(words)
                            if len(toks) != len(words) - 1
                            else " ".join(toks[:i] + [words[i]] + toks[i:])
                        )
                    else:
                        lm.corrected_text = lm.ocr_text
            out = adapter_for_format(doc.source_format).rewrite_file(
                tmp, doc.pages, "hans", "ins"
            )
            res = etree.fromstring(out.xml_bytes)
        except Exception as e:  # noqa: BLE001 -- un corpus qui casse le parseur est un résultat
            print("   ", path.name, type(e).__name__, e)
            continue
        for el in res.iter():
            if _local(el) != "TextLine" or el.get("ID") not in chosen:
                continue
            i = chosen[el.get("ID")]
            tw = truth[el.get("ID")].words
            st = [c for c in el if _local(c) == "String"]
            if len(st) != len(tw):
                continue
            unit = sum(w.width for w in tw) / sum(len(w.text) for w in tw)
            got = st[i]
            h, wd = int(got.get("HPOS")), int(got.get("WIDTH"))
            errs_l.append(abs(h - tw[i].hpos) / unit)
            errs_r.append(abs(h + wd - tw[i].right) / unit)
            n += 1
    if not n:
        print(f"{name:34s} {position:9s} rien")
        return
    q = lambda v, p: sorted(v)[min(len(v) - 1, int(p * len(v)))]
    ok = sum(1 for a, b in zip(errs_l, errs_r) if a <= 0.5 and b <= 0.5) / n
    print(
        f"{name:34s} {position:9s} n={n:4d}  bord gauche: méd {q(errs_l, 0.5):.2f} p90 {q(errs_l, 0.9):.2f} car.  bord droit: méd {q(errs_r, 0.5):.2f} p90 {q(errs_r, 0.9):.2f} car.  les deux ≤ 0,5 car. : {ok:.1%}"
    )


H = Path.home()
corpora = {
    "BnF 1836": [H / "cinoc/corpus/BnF-bpt6k3265015q/X0000002.xml"],
    "Gallica 1850-1890": sorted(
        (H / "saknussemm/tests/external_corpus/.cache").glob("*.xml")
    ),
    "37-GT-BNL 1868": sorted((H / "cinoc/corpus/37-GT-BNL").glob("*.xml")),
    "NewsEye 1937 Tesseract": sorted((H / "corpus-vt/newseye/ocr").glob("*.xml")),
    "BnL open data 1868": sorted((H / "corpus-reel/bnl-open").rglob("text/*.xml")),
}
for pos in ("intérieur", "début", "fin"):
    for name, files in corpora.items():
        run(name, files, pos)
    print()
