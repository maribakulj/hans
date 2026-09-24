"""Campagne — producteurs × prompts × modèles × résolutions, sur OCR17+ (9 pages) et NewsEye (6 pages dans le domaine).

    PYTHONPATH=~/saknussemm/src:~/saknussemm-demo/backend MISTRAL_KEY_FILE=… \\
      python tools/campagne.py <corpus> <producteur> <prompt> <modèle> [max_side]

Un bras = un fichier JSON dans ~/corpus-vt/resultats/campagne/, avec par ligne
(source, sortie, VT) et les métriques : CER, lignes changées / améliorées /
dégradées, lignes portant au moins un mot sans ancrage dans la source (proxy
d'invention, H19 addendum 2), lignes signalées par le proxy géométrique.
"""

from __future__ import annotations

import asyncio
import difflib
import io
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from lxml import etree
from PIL import Image, ImageDraw, ImageFont

from saknussemm import ChunkPlannerConfig, CorrectionPipeline, GuardConfig, load
from saknussemm.core.editing import EditScript
from saknussemm.core.schemas import ModelCapabilities
from saknussemm.integrations.llm import CORPUS_NOTE_EARLY_MODERN_FRENCH, with_corpus_notes
from saknussemm.producers.vision import (
    COMPOSITE_VISION_SYSTEM_PROMPT,
    PAGE_VISION_SYSTEM_PROMPT,
    VISION_SYSTEM_PROMPT,
    CompositeVisionEditProducer,
    ImagePart,
    PageVisionEditProducer,
    VisionEditProducer,
    _unalias_response,
    _xml_bbox_to_pixels,
    build_image_asset,
    edit_ops_from_response,
    line_aliases,
    open_page,
)
from app.providers.mistral_multimodal import MistralMultimodalProvider

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_saknussemm_ocr17 import RAW, Recorder, _lev, _lines, _lines_from_bytes, _simf  # noqa: E402
from run_saknussemm_newseye import BASE as NE, NOTE_1930, _alto_lines, _proxy  # noqa: E402

OUT = Path.home() / "corpus-vt" / "resultats" / "campagne"
INDOM = ["0401692-003", "Ce-soir_7635415_D0000002", "Marianne_7644869_D0000002",
         "Paris-Soir_7636525_D0000002", "Regards_7635838_D0000005", "Regards_7639182_D0000004"]
MODELS = {"small": "mistral-small-latest", "medium": "mistral-medium-latest", "large": "mistral-large-latest"}

REGION_PROMPT = """\
Tu es un moteur de correction post-OCR spécialisé dans les documents patrimoniaux.
L'IMAGE montre un EXTRAIT de la page : exactement les lignes listées dans le JSON,
dans l'ordre de lecture, de haut en bas. Le JSON donne chaque ligne avec son
identifiant et son texte OCR. Repère chaque ligne dans l'image d'après son texte
OCR et son rang, puis corrige-la d'après l'image.

Règles absolues :
1. Corrige uniquement les erreurs manifestes d'OCR, d'après l'image.
2. Conserve la langue source.
3. Conserve l'orthographe historique quand elle est réellement présente à l'image \
(ſ long, u pour v, ligatures) : ce n'est pas une erreur.
4. Ne traduis rien.
5. Ne modernise pas volontairement le texte.
6. Ne fusionne jamais deux lignes.
7. Ne scinde jamais une ligne.
8. Ne déplace jamais du texte d'une ligne à l'autre.
9. Chaque entrée line_id doit produire exactement une sortie avec le même line_id, \
recopié tel quel.
10. corrected_text doit contenir une seule ligne, sans caractère de saut de ligne.
11. Retourne uniquement un JSON valide conforme au schéma fourni.
12. En cas de doute ou d'image illisible, conserve le texte OCR (correction minimale).
13. N'invente jamais un caractère absent de l'image (pas d'hallucination visuelle).\
"""
REGION_IDS_PROMPT = REGION_PROMPT.replace(
    "Repère chaque ligne dans l'image d'après son texte\nOCR et son rang, puis corrige-la d'après l'image.",
    "Chaque ligne est PRÉCÉDÉE À GAUCHE, dans la marge, de son identifiant peint entre\n"
    "crochets, comme [K7QZP] : corrige chaque ligne d'après l'image de la ligne qui\nporte le MÊME identifiant.",
)
STRICT_NOTE = (
    "Ne remplace jamais un mot par un mot d'une autre forme : si un mot de l'OCR est "
    "illisible ou n'a pas de sens, garde-le tel quel plutôt que de deviner. Une "
    "correction ne change que des caractères à l'intérieur de mots que l'image confirme."
)
CORPUS_NOTE = {"ocr17": CORPUS_NOTE_EARLY_MODERN_FRENCH, "newseye": NOTE_1930}


class RegionVisionEditProducer(PageVisionEditProducer):
    """Le recadrage de la RÉGION du chunk (union des boîtes ALTO de ses lignes,
    marge 3 %), borné à ``max_side``, JPEG q90 ; avec ``paint_ids`` les alias
    sont peints dans la marge gauche, à la hauteur de chaque ligne."""

    wants_geometry: bool = True

    def __init__(self, provider: Any, api_key: str, model: str, *, system_prompt: str,
                 max_side: int = 2048, paint_ids: bool = False) -> None:
        super().__init__(provider, api_key, model, system_prompt=system_prompt, max_side=max_side)
        self._paint_ids = paint_ids
        from dataclasses import replace
        self.metadata = replace(self.metadata, name="region-vision" + ("-ids" if paint_ids else ""))

    async def produce(self, payload: Any, *, options: Any) -> tuple[EditScript, Any]:
        asset = payload.image_ref
        page = open_page(asset)
        boxes = {}
        for line in payload.lines:
            if line.geometry is not None:
                boxes[line.line_id] = _xml_bbox_to_pixels(line.geometry.coords, asset.transform)
        if not boxes:
            raise RuntimeError("région sans géométrie")
        left = min(b[0] for b in boxes.values()); top = min(b[1] for b in boxes.values())
        right = max(b[2] for b in boxes.values()); bottom = max(b[3] for b in boxes.values())
        mx, my = (right - left) * 0.03, (bottom - top) * 0.03
        gutter = 0.16 * (right - left) if self._paint_ids else 0
        x0, y0 = max(0, int(left - mx - gutter)), max(0, int(top - my))
        x1, y1 = min(page.width, int(right + mx)), min(page.height, int(bottom + my))
        crop = page.crop((x0, y0, x1, y1)).convert("RGB")
        aliases = line_aliases([ln.line_id for ln in payload.lines])
        if self._paint_ids:
            dr = ImageDraw.Draw(crop)
            h = max(14, int(sum(b[3] - b[1] for b in boxes.values()) / len(boxes) * 0.7))
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", h)
            except OSError:
                font = ImageFont.load_default()
            for lid, (bx0, by0, bx1, by1) in boxes.items():
                label = f"[{aliases[lid]}]"
                tw = dr.textlength(label, font=font)
                lx = max(2, bx0 - x0 - tw - 8); ly = by0 - y0 + (by1 - by0 - h) / 2
                dr.rectangle((lx - 3, ly - 2, lx + tw + 3, ly + h + 2), fill="white")
                dr.text((lx, ly), label, fill="black", font=font)
        if max(crop.size) > self._max_side:
            f = self._max_side / max(crop.size)
            crop = crop.resize((max(1, int(crop.width * f)), max(1, int(crop.height * f))), Image.Resampling.LANCZOS)
        buf = io.BytesIO(); crop.save(buf, format="JPEG", quality=90); data = buf.getvalue()
        import hashlib
        user_payload = {
            "task": payload.task, "document_id": payload.document_id, "page_id": payload.page_id,
            "lines": [{"line_id": aliases[ln.line_id], "ocr_text": ln.ocr_text,
                       **({"hyphenation_role": ln.hyphenation_role} if ln.hyphenation_role else {})}
                      for ln in payload.lines],
        }
        raw, usage = await self._provider.complete_structured_multimodal(
            api_key=self._api_key, model=self._model, system_prompt=self._system_prompt,
            user_payload=user_payload,
            images=[ImagePart(line_id="region", media_type="image/jpeg", data=data, sha256=hashlib.sha256(data).hexdigest())],
            json_schema=self._output_schema, temperature=options.temperature,
        )
        source_by_id = {ln.line_id: ln.ocr_text for ln in payload.lines}
        ops = edit_ops_from_response(
            _unalias_response(raw, {a: lid for lid, a in aliases.items()}, source_by_id), source_by_id=source_by_id
        )
        return EditScript(ops=ops), usage


def make_arm(corpus: str, producer: str, prompt: str, model_key: str, key: str, max_side: int | None) -> dict[str, Any]:
    vlm = MistralMultimodalProvider(); model = MODELS[model_key]
    notes = [CORPUS_NOTE[corpus]] + ([STRICT_NOTE] if prompt == "strict" else []) if prompt != "nu" else []
    planner = ChunkPlannerConfig(max_lines_per_request=20, line_window_size=20, coalesce_blocks=True)
    guard = GuardConfig.vision(attachment_scope="page")
    if producer.startswith("page"):
        side = max_side or int(producer[4:] or 1024)
        prod = PageVisionEditProducer(vlm, key, model, system_prompt=with_corpus_notes(PAGE_VISION_SYSTEM_PROMPT, *notes), max_side=side)
    elif producer.startswith("regionids"):
        side = max_side or int(producer[9:] or 2048)
        prod = RegionVisionEditProducer(vlm, key, model, system_prompt=with_corpus_notes(REGION_IDS_PROMPT, *notes), max_side=side, paint_ids=True)
    elif producer.startswith("region"):
        side = max_side or int(producer[6:] or 2048)
        prod = RegionVisionEditProducer(vlm, key, model, system_prompt=with_corpus_notes(REGION_PROMPT, *notes), max_side=side)
    elif producer == "lines":
        prod = VisionEditProducer(vlm, key, model, system_prompt=with_corpus_notes(VISION_SYSTEM_PROMPT, *notes),
                                  capabilities=ModelCapabilities(text=True, vision=True, structured_output=True, max_images=8))
    elif producer == "composite":
        prod = CompositeVisionEditProducer(vlm, key, model, max_lines=20, system_prompt=with_corpus_notes(COMPOSITE_VISION_SYSTEM_PROMPT, *notes))
        guard = GuardConfig(attachment_scope="page")
    else:
        raise SystemExit(f"producteur inconnu : {producer}")
    return {"producer": prod, "guard": guard, "planner": planner}


_W = lambda s: [w for w in re.findall(r"[^\W\d_]+", s.lower()) if len(w) >= 3]  # noqa: E731


def unanchored(src: str, out: str) -> float:
    sw, ow = _W(src), _W(out)
    if not ow:
        return 0.0
    low = src.lower(); bad = 0
    for w in ow:
        if w in low or (sw and max(difflib.SequenceMatcher(None, w, x).ratio() for x in sw) >= 0.5):
            continue
        bad += 1
    return bad / len(ow)


def pages_of(corpus: str):
    if corpus == "ocr17":
        for d in sorted(RAW.iterdir()):
            if (d / "src.page.xml").exists() and (d / "ref.page.xml").exists():
                yield d.name, d / "src.page.xml", d / "image.png", d / "ref.page.xml"
    else:
        for name in INDOM:
            img = next(p for p in (NE / "val").rglob(f"{name}.*") if p.suffix in (".jpg", ".tif"))
            yield name, NE / "ocr" / f"{name}.xml", img, None


def judge(corpus: str, name: str, src_xml: Path, ref_xml: Path | None, out_bytes: bytes, vt_all: Any) -> dict[str, list[str]]:
    """{line_id: [source, sortie, VT]} pour les lignes jugeables."""
    if corpus == "ocr17":
        got = _lines_from_bytes(out_bytes); src, ref = _lines(src_xml), _lines(ref_xml)
        return {k: [src[k], got.get(k, src[k]), ref[k]] for k in src if k in ref and src[k].strip() and ref[k].strip()}
    src = {l["id"]: l for l in _alto_lines(etree.parse(str(src_xml)))}
    got = {l["id"]: l for l in _alto_lines(etree.fromstring(out_bytes))}
    gts = [l for l in vt_all[name]["lines"] if l["gt"]]
    texts = {}
    for lid, line in src.items():
        proxy, kind = _proxy(line, gts)
        if proxy is not None:
            texts[lid] = [line["text"], got.get(lid, line)["text"], proxy, kind]
    return texts


async def run(corpus: str, producer: str, prompt: str, model_key: str, max_side: int | None) -> None:
    key = Path(os.environ["MISTRAL_KEY_FILE"]).read_text().strip()
    arm = make_arm(corpus, producer, prompt, model_key, key, max_side)
    tag = f"{corpus}__{producer}{'' if max_side is None else max_side}__{prompt}__{model_key}"
    print(f"\n=== {tag} ===", flush=True)
    vt_all = json.load(open(Path.home() / "corpus-vt" / "resultats" / "newseye_pairs.json")) if corpus == "newseye" else None
    tot = dict(E=0, L=0, Es=0, changed=0, better=0, worse=0, unanchored=0, wrong=0, retries=0, chunks=0, fb_chunks=0, tin=0, tout=0)
    pages: dict[str, Any] = {}; t0 = time.time()
    for name, src_xml, img, ref_xml in pages_of(corpus):
        loaded = load(src_xml); page_id = loaded.manifest.pages[0].page_id; rec = Recorder()
        pipeline = CorrectionPipeline(producer=arm["producer"], observer=rec, config=arm["planner"], guard_config=arm["guard"])
        try:
            result = await pipeline.run(document_manifest=loaded.manifest, source_files=loaded.source_paths,
                                        page_images={page_id: build_image_asset(page_id, img)})
        except Exception as exc:  # noqa: BLE001
            print(f"  {name[:28]:<30} ÉCHEC {type(exc).__name__}: {str(exc)[:120]}", flush=True)
            pages[name] = {"error": f"{type(exc).__name__}: {exc}"[:300]}; continue
        texts = judge(corpus, name, src_xml, ref_xml, next(iter(result.corrected_files.values())), vt_all)
        p = dict(E=0, L=0, Es=0, changed=0, better=0, worse=0, unanchored=0, wrong=0)
        vts = {k: v[2] for k, v in texts.items()}
        for k, (s, o, vt, *_) in texts.items():
            es, e = _lev(s, vt), _lev(o, vt); p["E"] += e; p["Es"] += es; p["L"] += len(vt)
            if o != s:
                p["changed"] += 1; p["better"] += e < es; p["worse"] += e > es; p["unanchored"] += unanchored(s, o) > 0
                own = _simf(vt, o); best = max(((_simf(v2, o), j) for j, v2 in vts.items() if j != k), default=(0, None))
                if best[1] and best[0] > own + 0.15 and _simf(vt, vts[best[1]]) < 0.85:
                    p["wrong"] += 1
        for kk in p: tot[kk] += p[kk]
        tot["retries"] += result.retry_count; tot["chunks"] += result.total_chunks; tot["fb_chunks"] += result.fallback_chunks
        tot["tin"] += result.usage.input_tokens; tot["tout"] += result.usage.output_tokens
        pages[name] = {**{k: v for k, v in p.items()}, "cer_src": p["Es"] / p["L"], "cer_out": p["E"] / p["L"],
                       "retries": result.retry_count, "chunks": result.total_chunks, "fallback_chunks": result.fallback_chunks,
                       "fallback_reasons": dict(result.fallback_reasons), "texts": texts}
        print(f"  {name[:28]:<30} CER {p['Es']/p['L']:>6.2%} → {p['E']/p['L']:>6.2%}  changées={p['changed']} +{p['better']} -{p['worse']} "
              f"sans-ancrage={p['unanchored']} proxy-mal={p['wrong']} retries={result.retry_count} repli={result.fallback_chunks}  {time.time()-t0:.0f} s", flush=True)
        json.dump({"arm": tag, "partial": True, "pages": pages}, open(OUT / f"{tag}.json", "w"), ensure_ascii=False)
    summary = {"arm": tag, "corpus": corpus, "producer": producer, "prompt": prompt, "model": MODELS[model_key], "max_side": max_side,
               "cer_src": tot["Es"] / tot["L"], "cer_out": tot["E"] / tot["L"], **{k: tot[k] for k in ("changed", "better", "worse", "unanchored", "wrong", "retries", "chunks", "fb_chunks")},
               "tokens_in": tot["tin"], "tokens_out": tot["tout"], "seconds": round(time.time() - t0), "pages": pages}
    json.dump(summary, open(OUT / f"{tag}.json", "w"), ensure_ascii=False, indent=1)
    print(f"  ⇒ {tag}: CER {summary['cer_src']:.2%} → {summary['cer_out']:.2%} | changées {tot['changed']} (+{tot['better']} / -{tot['worse']}) | "
          f"sans-ancrage {tot['unanchored']} | proxy-mal {tot['wrong']} | retries {tot['retries']} | repli chunks {tot['fb_chunks']} | "
          f"jetons {tot['tin']}+{tot['tout']} | {summary['seconds']} s", flush=True)


if __name__ == "__main__":
    corpus, producer, prompt, model_key = sys.argv[1:5]
    side = int(sys.argv[5]) if len(sys.argv) > 5 else None
    raise SystemExit(asyncio.run(run(corpus, producer, prompt, model_key, side)))
