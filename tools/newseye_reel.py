"""Le test réel : un OCR imparfait, une vraie correction, des boîtes d'un autre producteur.

    .venv/bin/python tools/newseye_reel.py

Jusqu'ici (H21, H22) la vérité était fabriquée : un ALTO abîmé exprès, puis
réparé. Ici rien n'est fabriqué :

- la **source** est l'ALTO de Tesseract sur trois pages de presse
  (`~/corpus-vt/newseye/ocr/`), avec ses erreurs de lecture ET de découpage
  en mots ;
- la **correction** est le texte de la vérité terrain NewsEye, ligne à
  ligne — ce qu'un correcteur parfait rendrait ;
- la **vérité géométrique** est la boîte de chaque mot dans le PAGE de la
  vérité terrain (export Transkribus, mots cohérents avec le texte de ligne
  sur 2 336 lignes, blanc médian 13 à 22 px) : un autre producteur que
  Tesseract, jamais vu par le résolveur.

Une ligne Tesseract n'est jugée que si elle s'apparie **une à une** avec une
ligne de la vérité terrain (IoU ≥ 0,2 dans les deux sens) : le système
suppose la segmentation en lignes juste, c'est son domaine déclaré. Les
fusions et scissions de lignes sont comptées et laissées de côté.

Quatre bras, par le vrai ``rewrite_alto_file`` :

    avant       le prorata sur toute la ligne (un résolveur qui rend la
                géométrie d'avant la PR #167, interrogé en premier)
    ancré       saknussemm aujourd'hui, sans résolveur
    ancré+ctc   le CTC en DERNIER RECOURS (``last_resort=True``)
    ctc         le CTC interrogé en premier, l'ancré derrière

Métrique de H1 : le milieu du blanc rendu entre deux mots, contre le blanc
de la vérité terrain, en caractères ; part des frontières à ≤ 0,5.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hans.cuts import LineCuts
from hans.resolvers import CTCCutsResolver, ProportionalResolver

NE = Path.home() / "corpus-vt" / "newseye"
VT_DIR = NE / "val" / "ATR_ValidationSet_BnF_Newseye_M2+"
CUTS = Path.home() / "corpus-vt" / "resultats" / "cuts_newseye"
PAGES = ("0253902-001", "0401692-003", "752234-003")


def _q(el: etree._Element) -> str:
    return str(etree.QName(el).localname) if isinstance(el.tag, str) else ""


def src_lines(path: Path) -> dict[str, dict]:
    out = {}
    for el in etree.parse(str(path)).iter():
        if _q(el) != "TextLine":
            continue
        x, y, w, h = (
            int(float(el.get(k) or 0)) for k in ("HPOS", "VPOS", "WIDTH", "HEIGHT")
        )
        words = [c.get("CONTENT") for c in el if _q(c) == "String" and c.get("CONTENT")]
        if w > 0 and h > 0 and words:
            out[el.get("ID")] = {"box": (x, y, x + w, y + h), "text": " ".join(words)}
    return out


def vt_lines(path: Path) -> dict[str, dict]:
    out = {}
    for el in etree.parse(str(path)).iter():
        if _q(el) != "TextLine":
            continue
        words = []
        for w in el:
            if _q(w) != "Word":
                continue
            pts = next(c.get("points") for c in w if _q(c) == "Coords")
            xs = [int(p.split(",")[0]) for p in pts.split()]
            txt = next(
                (
                    u.text or ""
                    for te in w
                    if _q(te) == "TextEquiv"
                    for u in te
                    if _q(u) == "Unicode"
                ),
                "",
            )
            words.append((txt, min(xs), max(xs)))
        pts = next((c.get("points") for c in el if _q(c) == "Coords"), "")
        xy = [tuple(int(v) for v in p.split(",")) for p in pts.split()]
        if not words or not xy or any(" " in w[0] or not w[0] for w in words):
            continue
        xs, ys = [p[0] for p in xy], [p[1] for p in xy]
        out[el.get("id")] = {
            "box": (min(xs), min(ys), max(xs), max(ys)),
            "words": words,
            "text": " ".join(w[0] for w in words),
        }
    return out


def iou(a: tuple, b: tuple) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def pair(src: dict[str, dict], vt: dict[str, dict]) -> tuple[dict[str, str], int]:
    """{id source: id VT} pour les appariements un à un ; et le nombre d'écartés."""
    s2v: dict[str, list[str]] = defaultdict(list)
    v2s: dict[str, list[str]] = defaultdict(list)
    for sid, s in src.items():
        for vid, v in vt.items():
            if iou(s["box"], v["box"]) >= 0.2:
                s2v[sid].append(vid)
                v2s[vid].append(sid)
    pairs = {
        sid: vids[0]
        for sid, vids in s2v.items()
        if len(vids) == 1 and len(v2s[vids[0]]) == 1
    }
    return pairs, len(src) - len(pairs)


def lev(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


class _Before:
    """La géométrie d'avant la PR #167 : toute la ligne au prorata, toujours."""

    name = "avant"
    last_resort = False

    def __init__(self) -> None:
        self._inner = ProportionalResolver()

    def resolve(self, request):  # type: ignore[no-untyped-def]
        return self._inner.resolve(request)


def ctc_resolver(
    page: str, pairs: dict[str, str], *, last_resort: bool
) -> CTCCutsResolver | None:
    path = CUTS / f"{page}.json"
    if not path.exists():
        return None
    raw = json.loads(path.read_text())["lines"]
    cuts = {}
    for sid, vid in pairs.items():
        if vid in raw:
            entry = raw[vid]
            cuts[sid] = LineCuts(
                sid, entry["text"], tuple((int(a), int(b)) for a, b in entry["spans"])
            )
    return _Partial(cuts, last_resort=last_resort)


class _Partial(CTCCutsResolver):
    """Le CTC là où un décodage existe ; ailleurs il lève, et la couture retombe."""

    asked = 0

    def resolve(self, request):  # type: ignore[no-untyped-def]
        type(self).asked += 1
        return super().resolve(request)


def run_arm(
    page: str, pairs: dict[str, str], vt: dict[str, dict], resolver: object | None
):
    from saknussemm.formats.alto.rewriter import rewrite_alto_file
    from saknussemm.formats.loader import build_document_manifest

    path = NE / "ocr" / f"{page}.xml"
    doc = build_document_manifest([(path, path.name)])
    for pg in doc.pages:
        for lm in pg.lines:
            lm.corrected_text = (
                vt[pairs[lm.line_id]]["text"] if lm.line_id in pairs else lm.ocr_text
            )
    result = rewrite_alto_file(
        path, doc.pages, "hans", "newseye-reel", word_geometry=resolver
    )  # type: ignore[arg-type]
    boxes = {}
    for el in etree.fromstring(result.xml_bytes).iter():
        if _q(el) == "TextLine" and el.get("ID") in pairs:
            boxes[el.get("ID")] = [
                (
                    c.get("CONTENT"),
                    int(c.get("HPOS")),
                    int(c.get("HPOS")) + int(c.get("WIDTH")),
                )
                for c in el
                if _q(c) == "String"
            ]
    return boxes, result.rewriter_paths


def errors(out_words: list[tuple], vt_words: list[tuple]) -> list[float] | None:
    if len(out_words) != len(vt_words) or len(vt_words) < 2:
        return None
    chars = sum(len(w[0]) for w in vt_words) + len(vt_words) - 1
    unit = (vt_words[-1][2] - vt_words[0][1]) / chars
    if unit <= 0:
        return None
    errs = []
    for k in range(len(vt_words) - 1):
        mid = (out_words[k][2] + out_words[k + 1][1]) / 2
        lo, hi = sorted((vt_words[k][2], vt_words[k + 1][1]))
        errs.append((lo - mid if mid < lo else mid - hi if mid > hi else 0.0) / unit)
    return errs


def summary(errs: list[float]) -> str:
    if not errs:
        return "— | — | — | —"
    o = sorted(errs)
    return (
        f"{len(o)} | {sum(e <= 0.5 for e in o) / len(o):.1%} | "
        f"{sum(o) / len(o):.3f} | {o[int(0.9 * (len(o) - 1))]:.2f}"
    )


def main() -> int:
    arms = ("avant", "ancré", "ancré+ctc", "ctc")
    by: dict[tuple, list[float]] = defaultdict(list)
    counts: dict[str, int] = defaultdict(int)
    for page in PAGES:
        src = src_lines(NE / "ocr" / f"{page}.xml")
        vt = vt_lines(VT_DIR / f"{page}.xml")
        pairs, dropped = pair(src, vt)
        counts["lignes source"] += len(src)
        counts["appariées une à une"] += len(pairs)
        resolvers = {
            "avant": _Before(),
            "ancré": None,
            "ancré+ctc": ctc_resolver(page, pairs, last_resort=True),
            "ctc": ctc_resolver(page, pairs, last_resort=False),
        }
        print(
            f"{page}: {len(src)} lignes Tesseract, {len(vt)} lignes VT, "
            f"{len(pairs)} appariées une à une ({dropped} écartées)",
            flush=True,
        )
        for arm in arms:
            before = _Partial.asked
            boxes, paths = run_arm(page, pairs, vt, resolvers[arm])
            if arm in ("ancré+ctc", "ctc"):
                counts[f"appels au CTC, bras « {arm} »"] += _Partial.asked - before
            for sid, vid in pairs.items():
                e = errors(boxes.get(sid, []), vt[vid]["words"])
                path = paths.get(sid, "untouched")
                if e is None:
                    if arm == "ancré":
                        counts[
                            "lignes non jugeables (mots rendus ≠ mots VT, ou un seul mot)"
                        ] += 1
                    continue
                cer = lev(src[sid]["text"], vt[vid]["text"]) / max(
                    1, len(vt[vid]["text"])
                )
                band = (
                    "≤ 5 %"
                    if cer <= 0.05
                    else "5–15 %"
                    if cer <= 0.15
                    else "15–30 %"
                    if cer <= 0.30
                    else "> 30 %"
                )
                n_src, n_vt = len(src[sid]["text"].split()), len(vt[vid]["words"])
                kind = (
                    "mots ajoutés"
                    if n_vt > n_src
                    else "mots retirés"
                    if n_vt < n_src
                    else "même compte"
                )
                for key in (
                    ("chemin", path),
                    ("cer", band) if path == "slow_path" else None,
                    ("nature", kind) if path == "slow_path" else None,
                    ("tout", "toutes les lignes"),
                ):
                    if key:
                        by[(arm, *key)].extend(e)
                if arm == "ancré":
                    counts[f"lignes {path}"] += 1

    print("\n" + "\n".join(f"- {k} : {v}" for k, v in counts.items()))
    head = "| | frontières | ≤ 0,5 car. | moyenne (car.) | p90 (car.) |\n|---|---|---|---|---|"
    print("\n### Toutes les lignes appariées\n" + head)
    for arm in arms:
        print(f"| {arm} | {summary(by[(arm, 'tout', 'toutes les lignes')])} |")
    print("\n### Par chemin de réécriture (bras « ancré »)\n" + head)
    for p in ("untouched", "fast_path", "slow_path"):
        print(f"| {p} | {summary(by[('ancré', 'chemin', p)])} |")
    print("\n### Chemin lent seul — là où la géométrie est recalculée\n" + head)
    for arm in arms:
        print(f"| {arm} | {summary(by[(arm, 'chemin', 'slow_path')])} |")
    for title, group, keys in (
        (
            "Chemin lent, selon le taux d'erreur de la ligne source",
            "cer",
            ("≤ 5 %", "5–15 %", "15–30 %", "> 30 %"),
        ),
        (
            "Chemin lent, selon ce que la correction fait au nombre de mots",
            "nature",
            ("mots ajoutés", "mots retirés", "même compte"),
        ),
    ):
        print(
            f"\n### {title}\n| | bras | frontières | ≤ 0,5 car. | moyenne (car.) | p90 (car.) |\n|---|---|---|---|---|---|"
        )
        for k in keys:
            for arm in arms:
                print(f"| {k} | {arm} | {summary(by[(arm, group, k)])} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
