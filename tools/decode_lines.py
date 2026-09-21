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


def main() -> int:
    alto, image, out = (Path(a) for a in sys.argv[1:4])

    from kraken import rpred
    from kraken.containers import BaselineLine, Segmentation
    from kraken.lib.models import load_any
    from kraken.lib.util import open_image

    model_path = sys.argv[4] if len(sys.argv) > 4 else _default_model()
    lines = read_lines(alto)
    print(f"{alto.name}: {len(lines)} lignes", flush=True)

    bl = [
        BaselineLine(
            id=ln.line_id,
            baseline=[
                (ln.hpos, ln.vpos + int(ln.height * 0.8)),
                (ln.hpos + ln.width, ln.vpos + int(ln.height * 0.8)),
            ],
            boundary=[
                (ln.hpos, ln.vpos),
                (ln.hpos + ln.width, ln.vpos),
                (ln.hpos + ln.width, ln.vpos + ln.height),
                (ln.hpos, ln.vpos + ln.height),
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
    for rec, ln in zip(rpred.rpred(model, open_image(str(image)), seg), lines):
        text = str(rec)
        cuts = list(rec.cuts)
        if len(cuts) != len(text):
            print(f"  ! {ln.line_id}: {len(cuts)} cuts / {len(text)} car.", flush=True)
            continue
        payload[ln.line_id] = {
            "text": text,
            "spans": [[min(_xs(c)), max(_xs(c))] for c in cuts],
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
