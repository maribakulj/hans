"""NewsEye — l'ALTO Tesseract tel quel à travers saknussemm, jugé contre la VT par géométrie.

    PYTHONPATH=~/saknussemm/src:~/saknussemm-demo/backend MISTRAL_KEY_FILE=… \\
      python tools/run_saknussemm_newseye.py [bras…]

La configuration de production de H13 §2.9 : les boîtes, le texte et l'ordre
de Tesseract, et pour vérité terrain de chaque ligne Tesseract la
concaténation des lignes VT que sa boîte recouvre (IoU ≥ 0,2) — exactement
l'évaluation du script, pour que la comparaison soit propre.
"""

from __future__ import annotations

import asyncio
import difflib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from lxml import etree

from saknussemm import ChunkPlannerConfig, CorrectionPipeline, GuardConfig, load
from saknussemm.core.schemas import ModelCapabilities
from saknussemm.integrations.llm import with_corpus_notes
from saknussemm.producers.vision import (
    COMPOSITE_VISION_SYSTEM_PROMPT,
    VISION_SYSTEM_PROMPT,
    CompositeVisionEditProducer,
    VisionEditProducer,
    build_image_asset,
)

from app.providers.mistral_multimodal import MistralMultimodalProvider

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_saknussemm_ocr17 import Recorder, _lev, _simf  # noqa: E402

BASE = Path.home() / "corpus-vt" / "newseye"
OUT = Path.home() / "corpus-vt" / "resultats"
MODEL = "mistral-medium-latest"
NOTE_1930 = (
    "Ces pages sont de la presse française des années 1930, en petit corps : "
    "conserve la ponctuation et les césures en fin de ligne, ne complète pas les "
    "mots coupés, ne modernise rien."
)


def _alto_lines(root: Any) -> list[dict[str, Any]]:
    q = lambda e: etree.QName(e).localname  # noqa: E731
    out = []
    for el in root.iter():
        if not isinstance(el.tag, str) or q(el) != "TextLine":
            continue
        x, y, w, h = (int(float(el.get(k) or 0)) for k in ("HPOS", "VPOS", "WIDTH", "HEIGHT"))
        words = [c.get("CONTENT") for c in el if isinstance(c.tag, str) and q(c) == "String" and c.get("CONTENT")]
        if w <= 0 or h <= 0 or not words:
            continue
        out.append({"id": el.get("ID"), "box": [x, y, x + w, y + h], "text": " ".join(words)})
    return out


def _iou(a: list[int], b: list[int]) -> float:
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def _proxy(line: dict[str, Any], gts: list[dict[str, Any]]) -> tuple[str | None, str]:
    hits = sorted((g for g in gts if _iou(line["box"], g["box"]) >= 0.2), key=lambda g: (g["box"][1], g["box"][0]))
    if not hits:
        return None, "aucune"
    kind = "fusion" if len(hits) >= 2 else "1:1"
    return " ".join(h["gt"] for h in hits), kind


def _arms(key: str) -> dict[str, dict[str, Any]]:
    vlm = MistralMultimodalProvider()
    planner = ChunkPlannerConfig(max_lines_per_request=20, line_window_size=20, coalesce_blocks=True)
    return {
        "composite·note1930·page·regroupé": dict(
            producer=CompositeVisionEditProducer(
                vlm, key, MODEL, max_lines=20,
                system_prompt=with_corpus_notes(COMPOSITE_VISION_SYSTEM_PROMPT, NOTE_1930),
            ),
            guard=GuardConfig(attachment_scope="page"),
            planner=planner,
        ),
        "vision-lines·note1930·vision(page)": dict(
            producer=VisionEditProducer(
                vlm, key, MODEL,
                system_prompt=with_corpus_notes(VISION_SYSTEM_PROMPT, NOTE_1930),
                capabilities=ModelCapabilities(text=True, vision=True, structured_output=True, max_images=8),
            ),
            guard=GuardConfig.vision(attachment_scope="page"),
            planner=planner,
        ),
    }


async def _run_arm(name: str, arm: dict[str, Any]) -> None:
    print(f"\n=== {name} ===", flush=True)
    VT = json.load(open(OUT / "newseye_pairs.json"))
    tot = {"E": 0, "L": 0, "Es": 0, "acc": 0, "wrong": 0, "retries": 0, "chunks": 0, "fb_chunks": 0, "in": 0, "out": 0}
    by_kind: dict[str, list[int]] = {}
    fallback: dict[str, int] = {}
    events: dict[str, int] = {}
    pages: dict[str, Any] = {}
    t0 = time.time()
    for name_page in sorted(VT):
        alto = BASE / "ocr" / f"{name_page}.xml"
        img = next(p for p in (BASE / "val").rglob(f"{name_page}.*") if p.suffix in (".jpg", ".tif"))
        loaded = load(alto)
        page_id = loaded.manifest.pages[0].page_id
        rec = Recorder()
        pipeline = CorrectionPipeline(producer=arm["producer"], observer=rec, config=arm["planner"], guard_config=arm["guard"])
        try:
            result = await pipeline.run(
                document_manifest=loaded.manifest,
                source_files=loaded.source_paths,
                page_images={page_id: build_image_asset(page_id, img)},
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  {name_page:<28} ÉCHEC {type(exc).__name__}: {str(exc)[:120]}", flush=True)
            pages[name_page] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
            continue
        src = {l["id"]: l for l in _alto_lines(etree.parse(str(alto)))}
        got = {l["id"]: l for l in _alto_lines(etree.fromstring(next(iter(result.corrected_files.values()))))}
        gts = [l for l in VT[name_page]["lines"] if l["gt"]]
        dec = {o.line_id: [o.decision.status, o.decision.reason.code if o.decision.reason else None] for o in result.report.lines}
        pE = pL = pEs = 0
        proxies = {}
        for lid, line in src.items():
            proxy, kind = _proxy(line, gts)
            if proxy is None:
                continue
            proxies[lid] = proxy
        texts = {}
        for lid, proxy in proxies.items():
            s, o = src[lid]["text"], got.get(lid, src[lid])["text"]
            kind = _proxy(src[lid], gts)[1]
            e, es, l = _lev(o, proxy), _lev(s, proxy), len(proxy)
            b = by_kind.setdefault(kind, [0, 0, 0, 0]); b[0] += 1; b[1] += es; b[2] += e; b[3] += l
            pE += e; pEs += es; pL += l
            texts[lid] = [s, o, proxy, kind, dec.get(lid)]
            if o != s:
                tot["acc"] += 1
                own = _simf(proxy, o)
                best = max(((_simf(p2, o), j) for j, p2 in proxies.items() if j != lid), default=(0, None))
                if best[1] and best[0] > own + 0.15 and _simf(proxy, proxies[best[1]]) < 0.85:
                    tot["wrong"] += 1
                    print(f"      ! mal rattachée {lid} [{kind}] « {o[:48]} »", flush=True)
        tot["E"] += pE; tot["L"] += pL; tot["Es"] += pEs
        for r, n in result.fallback_reasons.items():
            fallback[r] = fallback.get(r, 0) + n
        for t, n in rec.counts().items():
            events[t] = events.get(t, 0) + n
        tot["retries"] += result.retry_count; tot["chunks"] += result.total_chunks; tot["fb_chunks"] += result.fallback_chunks
        tot["in"] += result.usage.input_tokens; tot["out"] += result.usage.output_tokens
        pages[name_page] = {
            "cer_src": pEs / pL, "cer_out": pE / pL, "chunks": result.total_chunks, "retries": result.retry_count,
            "fallback_chunks": result.fallback_chunks, "fallback_lines": result.fallback_lines,
            "review_lines": result.review_lines, "fallback_reasons": dict(result.fallback_reasons),
            "events": rec.counts(), "texts": texts,
        }
        print(
            f"  {name_page:<28} CER {pEs/pL:>6.2%} → {pE/pL:>6.2%}  chunks={result.total_chunks} retries={result.retry_count} "
            f"repli_chunks={result.fallback_chunks} repli_lignes={result.fallback_lines} revue={result.review_lines}  {time.time()-t0:.0f} s",
            flush=True,
        )
        json.dump({"arm": name, "partial": True, "pages": pages}, open(OUT / f"sak_newseye_{name.replace('·','_').replace('()','')}.json", "w"), ensure_ascii=False)
    summary = {
        "arm": name, "cer_src": tot["Es"] / tot["L"], "cer_out": tot["E"] / tot["L"], "changed": tot["acc"], "mis_attached": tot["wrong"],
        "chunks": tot["chunks"], "retries": tot["retries"], "fallback_chunks": tot["fb_chunks"], "fallback_reasons": fallback,
        "events": events, "tokens_in": tot["in"], "tokens_out": tot["out"], "seconds": round(time.time() - t0),
        "by_kind": {k: {"lines": v[0], "cer_src": v[1] / v[3], "cer_out": v[2] / v[3]} for k, v in by_kind.items()}, "pages": pages,
    }
    json.dump(summary, open(OUT / f"sak_newseye_{name.replace('·','_').replace('()','')}.json", "w"), ensure_ascii=False, indent=1)
    print(
        f"  ⇒ CER {summary['cer_src']:.2%} → {summary['cer_out']:.2%} | changées {tot['acc']} | MAL R. {tot['wrong']} | chunks {tot['chunks']} | "
        f"retries {tot['retries']} | repli chunks {tot['fb_chunks']} | replis {fallback} | événements {events} | "
        f"jetons {tot['in']}+{tot['out']} | {summary['seconds']} s\n  par type : " + ", ".join(f"{k} {v['lines']} l. {v['cer_src']:.1%}→{v['cer_out']:.1%}" for k, v in summary["by_kind"].items()),
        flush=True,
    )


async def main() -> int:
    key = Path(os.environ["MISTRAL_KEY_FILE"]).read_text().strip()
    arms = _arms(key)
    for name in (sys.argv[1:] or list(arms)):
        await _run_arm(name, arms[name])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
