"""Des ALTO corrigés à regarder à l'œil nu, avant et après la PR #167.

    .venv/bin/python tools/visu_alto.py --src ~/saknussemm/src --tag apres  OUT
    .venv/bin/python tools/visu_alto.py --src <worktree main>/src --tag avant OUT

Pour chaque page (ALTO + image), le script :

1. corrompt une ligne sur quatre par une FUSION de deux mots voisins
   (les deux Strings collées, l'union comme boîte, le SP retiré) et une
   ligne sur quatre par une INVENTION (un mot retiré, String et SP) ;
2. donne à ces lignes leur texte d'origine comme correction, aux autres
   leur propre texte (chemin UNTOUCHED : rien ne bouge) ;
3. réécrit avec ``rewrite_alto_file`` de la bibliothèque trouvée dans
   ``--src`` — la branche de la PR pour « après », ``main`` pour « avant » ;
4. écrit, à côté de l'image, ``original.xml``, ``corrompu.xml``,
   ``<tag>.xml`` et ``touched.tsv`` (ID de ligne, action, mots concernés).

Ce qu'il faut regarder : sur les lignes de ``touched.tsv``, les boîtes des
mots voisins ne doivent pas avoir bougé, et la coupe (ou le mot remis) doit
tomber dans le blanc. Les lignes absentes de ``touched.tsv`` sont livrées
telles quelles.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hans.alto import read_lines


def _local(el: etree._Element) -> str:
    return str(etree.QName(el).localname) if isinstance(el.tag, str) else ""


def _strings(el: etree._Element) -> list[etree._Element]:
    return [c for c in el if _local(c) == "String"]


def _glue(el: etree._Element, i: int) -> None:
    strings = _strings(el)
    a, b = strings[i], strings[i + 1]
    a_h = int(float(a.get("HPOS")))
    b_right = int(float(b.get("HPOS"))) + int(float(b.get("WIDTH")))
    a.set("CONTENT", (a.get("CONTENT") or "") + (b.get("CONTENT") or ""))
    a.set("WIDTH", str(b_right - a_h))
    sib = a.getnext()
    while sib is not None and sib is not b:
        nxt = sib.getnext()
        el.remove(sib)
        sib = nxt
    el.remove(b)


def _drop(el: etree._Element, i: int) -> None:
    w = _strings(el)[i]
    sib = w.getnext()
    prev = w.getprevious()
    if sib is not None and _local(sib) == "SP":
        el.remove(sib)
    elif prev is not None and _local(prev) == "SP":
        el.remove(prev)
    el.remove(w)


def process(alto: Path, image: Path, out: Path, src: Path, tag: str) -> str:
    sys.path.insert(0, str(src))
    from saknussemm.formats.loader import adapter_for_format, build_document_manifest

    lines = read_lines(alto)
    truth = {ln.line_id: ln for ln in lines}
    ids = [ln.line_id for ln in lines]
    if len(set(ids)) != len(ids):
        return f"{alto.name}: identifiants de ligne dupliqués, page sautée"

    tree = etree.parse(str(alto))
    root = tree.getroot()
    by_id = {el.get("ID"): el for el in root.iter() if _local(el) == "TextLine"}
    touched: list[tuple[str, str, str]] = []
    for k, ln in enumerate(lines):
        el = by_id.get(ln.line_id)
        if el is None or len(ln.words) < 3 or len(_strings(el)) != len(ln.words):
            continue
        n = len(ln.words)
        if k % 4 == 0:
            i = n // 2 - 1
            _glue(el, i)
            touched.append(
                (ln.line_id, "fusion", f"{ln.words[i].text} | {ln.words[i + 1].text}")
            )
        elif k % 4 == 2:
            i = n // 2
            _drop(el, i)
            touched.append((ln.line_id, "invention", ln.words[i].text))

    out.mkdir(parents=True, exist_ok=True)
    corrupted = out / "corrompu.xml"
    tree.write(str(corrupted), xml_declaration=True, encoding=tree.docinfo.encoding)
    if not (out / "original.xml").exists():
        shutil.copy(alto, out / "original.xml")
    link = out / ("image" + image.suffix.lower())
    if not link.exists():
        link.symlink_to(image.resolve())

    wanted = {lid: (action, what) for lid, action, what in touched}
    doc = build_document_manifest([(corrupted, corrupted.name)])
    for page in doc.pages:
        for lm in page.lines:
            if lm.line_id in wanted:
                lm.corrected_text = " ".join(w.text for w in truth[lm.line_id].words)
            else:
                lm.corrected_text = lm.ocr_text
    result = adapter_for_format(doc.source_format).rewrite_file(
        corrupted, doc.pages, "hans", f"visu-{tag}"
    )
    (out / f"{tag}.xml").write_bytes(result.xml_bytes)
    (out / "touched.tsv").write_text(
        "ligne\taction\tmots\n" + "".join(f"{a}\t{b}\t{c}\n" for a, b, c in touched),
        encoding="utf-8",
    )
    return f"{alto.name}: {len(touched)} lignes touchées -> {out / (tag + '.xml')}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="visu_alto")
    parser.add_argument(
        "config", type=Path, help="JSON: {corpus: [[alto, image], ...]}"
    )
    parser.add_argument("out", type=Path)
    parser.add_argument(
        "--src", type=Path, required=True, help="src/ de la saknussemm à utiliser"
    )
    parser.add_argument("--tag", required=True, help="avant | apres")
    args = parser.parse_args(argv)
    spec = json.loads(args.config.read_text(encoding="utf-8"))
    for corpus, pairs in spec.items():
        for alto, image in pairs:
            alto, image = Path(alto).expanduser(), Path(image).expanduser()
            out = args.out / corpus / alto.stem
            try:
                print(process(alto, image, out, args.src.expanduser(), args.tag))
            except Exception as exc:  # noqa: BLE001 -- une page qui casse est un résultat
                print(f"{alto.name}: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
