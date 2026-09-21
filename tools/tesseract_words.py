"""Les boîtes au mot de Tesseract, rangées par ligne ALTO.

    tesseract page.jpg out -l fra tsv
    python tools/tesseract_words.py <alto.xml> <out.tsv> <sortie.json> [--scale S]

Vingt ans de segmentation en mots, déjà réglés. On ne redessine rien : on
prend les boîtes de Tesseract et on les attribue à la ligne ALTO qui les
contient. Le cache sort en coordonnées ALTO.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from hans.alto import read_lines  # noqa: E402


def main() -> int:
    alto, tsv, out = (Path(a) for a in sys.argv[1:4])
    argv = sys.argv[4:]
    scale = float(argv[argv.index("--scale") + 1]) if "--scale" in argv else 1.0

    words = []
    with tsv.open(encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh, delimiter="\t", quoting=csv.QUOTE_NONE):
            txt = (row.get("text") or "").strip()
            try:
                conf = float(row.get("conf") or -1)
            except ValueError:
                conf = -1
            if not txt or conf < 0:
                continue
            l, t = int(row["left"]), int(row["top"])
            w, h = int(row["width"]), int(row["height"])
            words.append((txt, l / scale, t / scale, w / scale, h / scale))

    lines = read_lines(alto)
    payload: dict[str, dict] = {}
    for ln in lines:
        y0, y1 = ln.vpos, ln.vpos + ln.height
        x0, x1 = ln.hpos, ln.hpos + ln.width
        inside = [
            (txt, l, w)
            for txt, l, t, w, h in words
            if y0 <= t + h / 2 <= y1 and x0 <= l + w / 2 <= x1
        ]
        inside.sort(key=lambda r: r[1])
        if inside:
            payload[ln.line_id] = {
                "text": " ".join(t for t, _, _ in inside),
                "boxes": [[round(l), round(l + w)] for _, l, w in inside],
            }
    out.write_text(json.dumps({"lines": payload}, ensure_ascii=False), encoding="utf-8")
    hit = sum(len(v["boxes"]) for v in payload.values())
    print(f"{len(payload)}/{len(lines)} lignes, {hit} mots attribués -> {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
