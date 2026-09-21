"""Les blancs entre les mots, mesurés dans l'encre. Sans modèle.

    python tools/ink_gaps.py <alto.xml> <image> <sortie.json> [--scale S]

Un profil de projection verticale par ligne : pour chaque colonne de pixels du
crop, combien d'encre. Un mot est une bosse, un blanc inter-mot un creux. La
méthode est celle de l'OCR d'avant les réseaux, elle coûte des millisecondes,
et elle mesure exactement ce qu'on cherche au lieu de l'inférer.

Le cache est écrit dans les coordonnées de l'ALTO, jamais en pixels image :
le banc mesure là-dedans, et un corpus en dixièmes de millimètre ne doit pas
contaminer le résolveur.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from hans.alto import read_lines  # noqa: E402


def gaps_of(crop, min_run: int) -> list[tuple[int, int]]:
    """Les creux d'encre du crop, en abscisses locales.

    Seuil d'Otsu sur le crop lui-même, pas une constante : le fond d'un scan
    patrimonial va du crème au gris sale, et un seuil fixe transforme une
    page sombre en un unique pâté sans aucun blanc.
    """
    import numpy as np

    a = np.asarray(crop.convert("L"), dtype=np.uint8)
    if a.size == 0:
        return []
    hist = np.bincount(a.ravel(), minlength=256).astype(float)
    total = hist.sum()
    omega = np.cumsum(hist) / total
    mu = np.cumsum(hist * np.arange(256)) / total
    mu_t = mu[-1]
    denom = omega * (1 - omega)
    denom[denom == 0] = 1e-9
    sigma_b = (mu_t * omega - mu) ** 2 / denom
    thr = int(np.argmax(sigma_b))

    ink = (a <= thr).sum(axis=0)  # encre par colonne
    blank = ink == 0
    out: list[tuple[int, int]] = []
    start = None
    for x, b in enumerate(blank):
        if b and start is None:
            start = x
        elif not b and start is not None:
            if x - start >= min_run:
                out.append((start, x))
            start = None
    if start is not None and len(blank) - start >= min_run:
        out.append((start, len(blank)))
    return out


def main() -> int:
    alto, image, out = (Path(a) for a in sys.argv[1:4])
    argv = sys.argv[4:]
    scale = float(argv[argv.index("--scale") + 1]) if "--scale" in argv else 1.0

    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None
    im = Image.open(image)
    lines = read_lines(alto)
    payload: dict[str, list[list[int]]] = {}
    for ln in lines:
        x0, y0 = round(ln.hpos * scale), round(ln.vpos * scale)
        x1, y1 = round((ln.hpos + ln.width) * scale), round(
            (ln.vpos + ln.height) * scale
        )
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(im.size[0], x1), min(im.size[1], y1)
        if x1 - x0 < 4 or y1 - y0 < 4:
            continue
        # un blanc inter-mot fait au moins ~1/8 de la hauteur de la ligne ;
        # en dessous c'est un espacement de lettres, pas une frontière
        min_run = max(2, (y1 - y0) // 8)
        g = gaps_of(im.crop((x0, y0, x1, y1)), min_run)
        # retour en coordonnées ALTO
        payload[ln.line_id] = [
            [round(x0 / scale + a / scale), round(x0 / scale + b / scale)] for a, b in g
        ]
    out.write_text(
        json.dumps({"alto": alto.name, "lines": payload}), encoding="utf-8"
    )
    print(f"{len(payload)} lignes -> {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
