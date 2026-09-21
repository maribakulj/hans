"""Decode a page's lines and dump one horizontal span per character.

Run with the kraken environment, NOT with hans's own:

    ~/outils-seg/kraken-env/bin/python tools/decode_lines.py \
        page.alto.xml page.jpg cuts.json

Why a separate process and a JSON artefact rather than a `hans[ctc]` extra:
torch and kraken weigh ~2 GB, the bench must stay installable in a CI that
has neither, and the cache makes a campaign auditable afterwards -- the text
the model produced sits on disk next to the numbers it produced.

It reads lines through `hans.alto`, the same reader the bench uses, so the
two cannot disagree about which lines exist or what they are called.

The `__main__` guard is load-bearing: kraken's predict path uses
multiprocessing, and without it every worker re-executes this file and the
machine spawns until it dies.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from hans.alto import read_lines  # noqa: E402


def _xs(cut: object) -> list[int]:
    """Kraken returns either a polygon or a flat pair, depending on version."""
    if isinstance(cut, (list, tuple)) and cut and isinstance(cut[0], (list, tuple)):
        return [int(p[0]) for p in cut]
    return [int(v) for v in cut]  # type: ignore[union-attr]


def _page_width(alto: Path) -> int | None:
    """The ALTO's own declared page width, when it has one."""
    from lxml import etree

    for el in etree.parse(str(alto)).iter():
        if isinstance(el.tag, str) and etree.QName(el).localname == "Page":
            raw = el.get("WIDTH")
            return int(float(raw)) if raw else None
    return None


def _check_scale(
    lines: list, img_width: int, scale: float, page_width: int | None
) -> None:
    """Refuse to decode when the declared scale contradicts the image.

    The 37-GT-BNL ALTO are in tenths of a millimetre at 300 dpi, so their
    coordinates are 254/300 of the pixels. Decoding them at scale 1 does not
    fail: it crops 18% short, further off with every line down the page, and
    returns text — plausible, never empty. That trap has already cost
    saknussemm two full campaigns, twice, which is why this refuses instead
    of warning.
    """
    # The reference is the ALTO's DECLARED page width when it has one. The
    # first version of this guard compared against the rightmost line
    # instead, and would have refused a perfectly scaled corpus at 1.247
    # simply because no line reaches the page edge — a guard that cries
    # wolf gets switched off, which is worse than no guard.
    if page_width:
        reference, what = page_width, "la largeur de page declaree"
        tolerance = 0.02
    else:
        reference = max(ln.hpos + ln.width for ln in lines)
        what = "l'etendue des lignes (la page ne declare pas de WIDTH)"
        # Lines never reach both edges, so the implied ratio is an
        # OVER-estimate here; only a gross mismatch is actionable.
        tolerance = 0.30
    implied = img_width / reference
    if abs(implied - scale) > tolerance:
        raise SystemExit(
            f"ECHELLE INCOHERENTE : l'image fait {img_width} px, {what} vaut "
            f"{reference}, soit un rapport de {implied:.3f} — or --scale vaut "
            f"{scale:.3f}. 300/254 = 1.181 (dixiemes de mm a 300 dpi). "
            "Rien n'a ete decode."
        )


def main() -> int:
    alto, image, out = (Path(a) for a in sys.argv[1:4])
    scale = 1.0
    argv = sys.argv[4:]
    if "--scale" in argv:
        scale = float(argv[argv.index("--scale") + 1])

    from kraken import rpred
    from kraken.containers import BaselineLine, Segmentation
    from kraken.lib.models import load_any
    from kraken.lib.util import open_image

    model_path = _default_model()
    lines = read_lines(alto)
    print(f"{alto.name}: {len(lines)} lignes, echelle {scale:.3f}", flush=True)

    im = open_image(str(image))
    _check_scale(lines, im.size[0], scale, _page_width(alto))


    # Clamp into the image, or kraken silently returns an EMPTY read for
    # the line. Measured on 37-GT-BNL, 2026-09-21: of 509 lines, the 364
    # that fell wholly inside were all read and the 145 that touched an
    # edge were ALL empty — a perfect split. The crops were legible; the
    # polygon extractor simply cannot take one that leaves the image. An
    # empty read costs no error, it just makes the resolver decline and
    # hand the line back to the incumbent, so this was quietly measuring
    # the baseline on 28% of that corpus and calling it the candidate.
    img_w, img_h = im.size

    def sx(v: float) -> int:
        return max(0, min(img_w - 1, int(round(v * scale))))

    def sy(v: float) -> int:
        return max(0, min(img_h - 1, int(round(v * scale))))

    bl = [
        BaselineLine(
            id=ln.line_id,
            baseline=[
                (sx(ln.hpos), sy(ln.vpos + ln.height * 0.8)),
                (sx(ln.hpos + ln.width), sy(ln.vpos + ln.height * 0.8)),
            ],
            boundary=[
                (sx(ln.hpos), sy(ln.vpos)),
                (sx(ln.hpos + ln.width), sy(ln.vpos)),
                (sx(ln.hpos + ln.width), sy(ln.vpos + ln.height)),
                (sx(ln.hpos), sy(ln.vpos + ln.height)),
            ],
        )
        for ln in lines
    ]
    seg = Segmentation(
        type="baselines",
        imagename=str(image),
        text_direction="horizontal-lr",
        script_detection=False,
        lines=bl,
    )

    model = load_any(model_path)
    payload: dict[str, dict[str, object]] = {}
    for rec, ln in zip(rpred.rpred(model, im, seg), lines):
        text = str(rec)
        cuts = list(rec.cuts)
        if len(cuts) != len(text):
            print(f"  ! {ln.line_id}: {len(cuts)} cuts / {len(text)} car.", flush=True)
            continue
        payload[ln.line_id] = {
            "text": text,
            # back to ALTO units: the cache is always in the coordinate
            # system the bench measures in, so no resolver needs to know
            # that this corpus was ever scaled
            "spans": [
                [round(min(_xs(c)) / scale), round(max(_xs(c)) / scale)]
                for c in cuts
            ],
        }

    out.write_text(
        json.dumps({"alto": alto.name, "lines": payload}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"-> {out} ({len(payload)}/{len(lines)} lignes)", flush=True)
    return 0


def _default_model() -> str:
    import glob

    hits = glob.glob(
        str(
            Path.home()
            / "Library/Application Support/htrmopo/*/catmus-print-fondue-large.mlmodel"
        )
    )
    if not hits:
        raise SystemExit("modèle CATMuS-Print absent : kraken get 10.5281/zenodo.10592716")
    return hits[0]


if __name__ == "__main__":
    raise SystemExit(main())
