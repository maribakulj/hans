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

from hans.alto import read_lines, read_page_lines  # noqa: E402


def _xs(cut: object) -> list[int]:
    """Kraken returns either a polygon or a flat pair, depending on version."""
    if isinstance(cut, (list, tuple)) and cut and isinstance(cut[0], (list, tuple)):
        return [int(p[0]) for p in cut]
    return [int(v) for v in cut]  # type: ignore[union-attr]


def _page_width(alto: Path) -> int | None:
    """The declared page width (ALTO @WIDTH, or PAGE @imageWidth)."""
    from lxml import etree

    for el in etree.parse(str(alto)).iter():
        if isinstance(el.tag, str) and etree.QName(el).localname == "Page":
            raw = el.get("WIDTH") or el.get("imageWidth")
            return int(float(raw)) if raw else None
    return None


def _check_scale(
    lines: list,
    img_width: int,
    scale: float,
    page_width: int | None,
    scale_was_given: bool = True,
) -> None:
    """Refuse to decode when the scale cannot be trusted.

    The trap: an ALTO in tenths of a millimetre at 300 dpi holds 254/300 of
    the pixels, so decoding it at scale 1 crops 18% short, further off with
    every line down the page, and returns text -- plausible, never empty. It
    has cost saknussemm two full campaigns, twice.

    Two regimes, because only one of them can actually be checked:

    - **The ALTO declares a page width.** Then the ratio is knowable and is
      held to 2%.
    - **It does not.** Then the rightmost line is all there is, and it is an
      UNDER-estimate of the page: 37-GT-BNL implies 1.181 with a true scale
      of 1.181, while the pinned Gallica implies 1.247 with a true scale of
      1.0. The heuristic cannot tell those apart -- so this does not guess.
      It requires ``--scale`` to be stated and records what the lines imply.

    That last rule exists because the guard's second version tried to guess
    and silently stopped catching the very corpus it was written for: widening
    the tolerance to kill a false positive killed the true positive with it.
    A test now pins both directions.
    """
    if page_width:
        implied = img_width / page_width
        if abs(implied - scale) > 0.02:
            raise SystemExit(
                f"ECHELLE INCOHERENTE : l'image fait {img_width} px, la page "
                f"declare {page_width}, soit un rapport de {implied:.3f} — or "
                f"--scale vaut {scale:.3f}. Rien n'a ete decode."
            )
        return

    extent = max(ln.hpos + ln.width for ln in lines)
    implied = img_width / extent
    if not scale_was_given:
        raise SystemExit(
            f"ECHELLE INVERIFIABLE : cet ALTO ne declare pas de WIDTH de page, "
            f"donc l'echelle ne peut pas etre deduite — la ligne la plus a "
            f"droite ne donne qu'une borne ({implied:.3f}, sur-estimation). "
            "Passer --scale explicitement. 300/254 = 1.1811 pour un ALTO en "
            "dixiemes de millimetre a 300 dpi. Rien n'a ete decode."
        )
    print(
        f"  echelle {scale:.4f} declaree ; les lignes impliquent au plus "
        f"{implied:.3f} (borne, la page ne declare pas sa largeur)",
        flush=True,
    )


def main() -> int:
    alto, image, out = (Path(a) for a in sys.argv[1:4])
    argv = sys.argv[4:]
    scale_was_given = "--scale" in argv
    scale = float(argv[argv.index("--scale") + 1]) if scale_was_given else 1.0

    from kraken import rpred
    from kraken.containers import BaselineLine, Segmentation
    from kraken.lib.models import load_any
    from kraken.lib.util import open_image

    model_path = (
        argv[argv.index("--model") + 1] if "--model" in argv else _default_model()
    )
    reader = read_page_lines if alto.read_text(errors="replace")[:4000].find("PcGts") >= 0 else read_lines
    lines = reader(alto)
    print(f"{alto.name}: {len(lines)} lignes, echelle {scale:.3f}", flush=True)

    im = open_image(str(image))
    _check_scale(lines, im.size[0], scale, _page_width(alto), scale_was_given)


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
