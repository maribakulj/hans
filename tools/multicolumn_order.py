"""H11 : le modèle réordonne-t-il les lignes d'une page multi-colonnes ?

    MISTRAL_KEY_FILE=<clé> python tools/multicolumn_order.py \
        <alto.xml> <image.jpg> <x0> <x1> <étiquette> [modèle]

Le recollage au caractère (`reproject_page_lines` de saknussemm) suppose que
le flux rendu reste **monotone**. Sur une page à six colonnes l'ordre ALTO
est colonne par colonne ; un modèle qui lirait l'image comme une trame
rendrait un tout autre ordre. Cet outil le mesure sans vérité terrain : il
apparie chaque ligne rendue à sa source et compte les **inversions**.

Deux pièges payés en l'écrivant :

- les ALTO Gallica déclarent ``ISO-8859-1`` et contiennent de l'UTF-8. Sans
  la réparation, tout est du mojibake et l'appariement s'effondre ;
- une ligne d'**un seul mot** n'a pas de quoi être appariée quand ce mot
  existe ailleurs dans la page. Les 13 inversions de la campagne `medium`
  viennent toutes de « Tonkin. » — c'est la mesure qui se trompe, pas le
  modèle. Les lignes courtes sont comptées à part pour cette raison.
"""

from __future__ import annotations

import base64
import io
import json
import os
import sys
import urllib.request
from pathlib import Path

SYSTEM = (
    "Tu es un moteur de correction post-OCR pour la presse francaise du "
    "XIXe siecle.\n"
    "On te donne l'IMAGE d'un extrait de journal et la transcription OCR de "
    "ses lignes, une par ligne, dans l'ordre.\n"
    "Corrige chaque ligne en t'appuyant sur l'image. Ne modernise rien, "
    "n'ajoute ni ne supprime de ligne.\n"
    "Rends EXACTEMENT autant de lignes que tu en recois, dans le meme ordre, "
    "sans numerotation."
)


def repair(text: str) -> str:
    """Le mojibake des ALTO Gallica, quand il est réparable."""
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


def band(alto: Path, top: int, bottom: int, x0: int, x1: int) -> list[dict]:
    """Les lignes entièrement contenues dans une fenêtre, en ordre document."""
    from lxml import etree

    def local(el: object) -> str:
        return str(etree.QName(el).localname)

    out: list[dict] = []
    for el in etree.parse(str(alto)).iter():
        if not isinstance(el.tag, str) or local(el) != "TextLine":
            continue
        v, h = int(el.get("VPOS") or 0), int(el.get("HEIGHT") or 0)
        x = int(el.get("HPOS") or 0)
        if not (top <= v and v + h <= bottom and x0 <= x < x1):
            continue
        words = [
            c.get("CONTENT")
            for c in el
            if isinstance(c.tag, str) and local(c) == "String" and c.get("CONTENT")
        ]
        if words:
            out.append(
                {
                    "id": el.get("ID"),
                    "hpos": x,
                    "vpos": v,
                    "text": repair(" ".join(w for w in words if w)),
                }
            )
    return out


def _tokens(text: str) -> set[str]:
    return {w for w in text.lower().split() if len(w) > 2}


def match(line: str, sources: list[str]) -> int | None:
    """L'indice source le plus proche par recouvrement de jetons, ou rien."""
    best, score = None, 0.0
    a = _tokens(line)
    for i, s in enumerate(sources):
        b = _tokens(s)
        j = len(a & b) / len(a | b) if a | b else 0.0
        if j > score:
            best, score = i, j
    return best


def inversions(sequence: list[int | None]) -> tuple[int, int]:
    """(inversions, paires) sur la suite des indices appariés."""
    seq = [x for x in sequence if x is not None]
    inv = sum(
        1 for a in range(len(seq)) for b in range(a + 1, len(seq)) if seq[a] > seq[b]
    )
    return inv, len(seq)


def raster_baseline(lines: list[dict], row: int = 45) -> int:
    """Le repère : ce que produirait une lecture en trame de la même bande."""
    order = sorted(
        range(len(lines)), key=lambda i: (lines[i]["vpos"] // row, lines[i]["hpos"])
    )
    return inversions(list(order))[0]


def call(b64: str, block: str, key: str, model: str) -> tuple[str, dict]:
    body = json.dumps(
        {
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": f"data:image/jpeg;base64,{b64}",
                        },
                        {"type": "text", "text": block},
                    ],
                },
            ],
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.mistral.ai/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=1800) as resp:
        payload = json.loads(resp.read())
    return payload["choices"][0]["message"]["content"], payload.get("usage", {})


def main() -> int:
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None
    alto, image = Path(sys.argv[1]), Path(sys.argv[2])
    x0, x1, tag = int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
    model = sys.argv[6] if len(sys.argv) > 6 else "mistral-medium-latest"
    top, bottom = 300, 2300
    key = Path(os.environ["MISTRAL_KEY_FILE"]).read_text().strip()

    lines = band(alto, top, bottom, x0, x1)
    if not lines:
        print("aucune ligne dans la bande", file=sys.stderr)
        return 1

    from lxml import etree

    page = next(
        el
        for el in etree.parse(str(alto)).iter()
        if isinstance(el.tag, str) and etree.QName(el).localname == "Page"
    )
    im = Image.open(image).convert("RGB")
    scale = im.size[0] / float(page.get("WIDTH") or im.size[0])
    crop = im.crop(
        (int(x0 * scale), int(top * scale), int(x1 * scale), int(bottom * scale))
    )
    if (s := 2048 / max(crop.size)) < 1:
        crop = crop.resize((int(crop.width * s), int(crop.height * s)), Image.LANCZOS)
    buf = io.BytesIO()
    crop.save(buf, "JPEG", quality=88)
    b64 = base64.b64encode(buf.getvalue()).decode()

    columns = len({line["hpos"] // 950 for line in lines})
    print(
        f"{tag}: {len(lines)} lignes, {columns} colonnes, crop {crop.size}\n"
        f"  repère lecture en trame: {raster_baseline(lines)} inversions",
        flush=True,
    )
    text, usage = call(b64, "\n".join(x["text"] for x in lines), key, model)
    returned = [x for x in text.split("\n") if x.strip()]
    sources = [x["text"] for x in lines]
    sequence = [match(x, sources) for x in returned]
    inv, matched = inversions(sequence)
    short = sum(
        1 for x, i in zip(returned, sequence) if i is not None and len(x.split()) <= 3
    )
    print(
        f"  rendu {len(returned)} lignes pour {len(lines)} reçues  usage={usage}\n"
        f"  appariées {matched}/{len(returned)} ({short} de 3 mots ou moins)\n"
        f"  INVERSIONS {inv} / {matched * (matched - 1) // 2} paires",
        flush=True,
    )
    Path(f"/tmp/multicol_{tag}.json").write_text(
        json.dumps(
            {"src": lines, "got": returned, "seq": sequence, "usage": usage},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
