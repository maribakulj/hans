"""OCR17+ à travers saknussemm lui-même — pas à côté.

    PYTHONPATH=~/saknussemm/src:~/saknussemm-demo/backend MISTRAL_KEY_FILE=… \\
      python tools/run_saknussemm_ocr17.py [bras…]

Six bras, même corpus (9 pages, VT humaine), même modèle. Ce que mes scripts
de campagne ne faisaient pas et que saknussemm fait : valider le compte de
lignes, retenter (rampe de température), redescendre PAGE → BLOCK → WINDOW →
LINE, passer les trois étages de garde et les passes document-wide. Tout est
observé par l'observateur et compté au rapport ; le script n'ajoute aucune
logique de correction, il mesure ce qui sort.
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

from saknussemm import (
    ChunkPlannerConfig,
    CorrectionPipeline,
    GuardConfig,

    load,
)
from saknussemm.core.schemas import ModelCapabilities
from saknussemm.integrations.page import PAGE_SYSTEM_PROMPT
from saknussemm.producers.page_llm import PageLLMEditProducer
from saknussemm.producers.vision import (
    CompositeVisionEditProducer,
    VisionEditProducer,
    build_image_asset,
)

from app.providers.mistral_multimodal import MistralMultimodalProvider
from app.providers.mistral_provider import MistralProvider

RAW = Path.home() / "corpus-vt" / "raw"
OUT = Path.home() / "corpus-vt" / "resultats"
MODEL = "mistral-medium-latest"
#: Ce que mes campagnes disaient au modèle et que le prompt générique ne dit pas.
PROMPT17 = (
    "\n15. Ces pages sont des imprimés français du XVIIe siècle : CONSERVE le s long (ſ), "
    "les graphies d'époque (eſtoit, ie, vn) et la ponctuation d'origine. Ne modernise rien."
)


def _line_text(el: Any) -> str:
    """The line's OWN TextEquiv, else its Words' — OCR17+ ground truth files
    carry the reread text on a single <Word> per line and no line TextEquiv;
    read as a line-level TextEquiv they come back empty, silently."""
    q = lambda e: etree.QName(e).localname  # noqa: E731
    for c in el:
        if isinstance(c.tag, str) and q(c) == "TextEquiv":
            for u in c:
                if isinstance(u.tag, str) and q(u) == "Unicode":
                    return (u.text or "").strip()
    parts = []
    for w in el:
        if isinstance(w.tag, str) and q(w) == "Word":
            for c in w:
                if isinstance(c.tag, str) and q(c) == "TextEquiv":
                    for u in c:
                        if isinstance(u.tag, str) and q(u) == "Unicode" and u.text:
                            parts.append(u.text)
    return " ".join(parts).strip()


def _lines_of_tree(root: Any) -> dict[str, str]:
    q = lambda e: etree.QName(e).localname  # noqa: E731
    return {
        (el.get("id") or ""): _line_text(el)
        for el in root.iter()
        if isinstance(el.tag, str) and q(el) == "TextLine"
    }


def _lines(path: Path) -> dict[str, str]:
    return _lines_of_tree(etree.parse(str(path)))


def _lev(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _simf(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.casefold(), b.casefold(), autojunk=False).ratio()


class Recorder:
    """Every engine event, kept; the counts the comparison needs, derived."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def on_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.append((event_type, payload))
        if event_type in ("retry", "chunk_downgraded", "chunk_error", "warning"):
            short = {k: (str(v)[:90]) for k, v in payload.items() if k != "chunk_id"}
            print(f"      · {event_type}: {short}", flush=True)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for t, _ in self.events:
            out[t] = out.get(t, 0) + 1
        return out


def _arms(key: str) -> dict[str, dict[str, Any]]:
    vlm = MistralMultimodalProvider()
    txt = MistralProvider()
    planner20 = ChunkPlannerConfig(max_lines_per_request=20, line_window_size=20)
    return {
        "vision-lines·vision()": dict(
            # Comme la démo : sans max_images déclaré, le batcher ne découpe
            # pas et Mistral refuse le 9e recadrage (400/3051) — vu au premier run.
            producer=VisionEditProducer(
                vlm, key, MODEL,
                capabilities=ModelCapabilities(
                    text=True, vision=True, structured_output=True,
                    max_images=MistralMultimodalProvider.MAX_IMAGES_PER_CALL,
                ),
            ),
            guard=GuardConfig.vision(),
            planner=None,
        ),
        "composite·adjacent": dict(
            producer=CompositeVisionEditProducer(vlm, key, MODEL, max_lines=20),
            guard=GuardConfig(),
            planner=planner20,
        ),
        "composite·page": dict(
            producer=CompositeVisionEditProducer(vlm, key, MODEL, max_lines=20),
            guard=GuardConfig(attachment_scope="page"),
            planner=planner20,
        ),
        "composite·page·jumelles": dict(
            producer=CompositeVisionEditProducer(vlm, key, MODEL, max_lines=20),
            guard=GuardConfig(attachment_scope="page", attachment_twin_similarity=0.85),
            planner=planner20,
        ),
        "page-aligned·jaccard·prompt17": dict(
            producer=PageLLMEditProducer(
                txt, key, MODEL, line_matching="jaccard",
                system_prompt=PAGE_SYSTEM_PROMPT + PROMPT17,
            ),
            guard=GuardConfig(),
            planner=None,
        ),
        "page-aligned·jaccard": dict(
            producer=PageLLMEditProducer(txt, key, MODEL, line_matching="jaccard"),
            guard=GuardConfig(),
            planner=None,
        ),
        "page-aligned·caractères·page": dict(
            producer=PageLLMEditProducer(txt, key, MODEL, line_matching="characters"),
            guard=GuardConfig(attachment_scope="page"),
            planner=None,
        ),
    }


async def _run_arm(name: str, arm: dict[str, Any]) -> dict[str, Any]:
    print(f"\n=== {name} ===", flush=True)
    per_page: dict[str, Any] = {}
    E = L = Es = acc = wrong = 0
    fallback: dict[str, int] = {}
    counts: dict[str, int] = {}
    retries = chunks = fb_chunks = 0
    usage_in = usage_out = 0
    t0 = time.time()
    for d in sorted(RAW.iterdir()):
        src_xml, ref_xml, img = d / "src.page.xml", d / "ref.page.xml", d / "image.png"
        if not (src_xml.exists() and ref_xml.exists() and img.exists()):
            continue
        loaded = load(src_xml)
        page_id = loaded.manifest.pages[0].page_id
        rec = Recorder()
        pipeline = CorrectionPipeline(
            producer=arm["producer"],
            observer=rec,
            config=arm["planner"],
            guard_config=arm["guard"],
        )
        try:
            result = await pipeline.run(
                document_manifest=loaded.manifest,
                source_files=loaded.source_paths,
                page_images={page_id: build_image_asset(page_id, img)},
            )
        except Exception as exc:  # noqa: BLE001 — le bras continue, l'échec est compté
            print(f"  {d.name[:28]:<30} ÉCHEC {type(exc).__name__}: {str(exc)[:100]}", flush=True)
            per_page[d.name] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
            continue
        out_bytes = next(iter(result.corrected_files.values()))
        got = _lines_from_bytes(out_bytes)
        src, ref = _lines(src_xml), _lines(ref_xml)
        ids = [k for k in src if k in ref and src[k].strip() and ref[k].strip()]
        pE = pL = pEs = 0
        for k in ids:
            final = got.get(k, src[k])
            pE += _lev(final, ref[k]); pEs += _lev(src[k], ref[k]); pL += len(ref[k])
            if final != src[k]:
                acc += 1
                own = _simf(ref[k], final)
                best = max(((_simf(ref[j], final), j) for j in ids if j != k), default=(0, None))
                if best[1] and best[0] > own + 0.15 and _simf(ref[k], ref[best[1]]) < 0.85:
                    wrong += 1
                    print(f"      ! mal rattachée {k}: « {final[:50]} »", flush=True)
        E += pE; L += pL; Es += pEs
        for r, n in result.fallback_reasons.items():
            fallback[r] = fallback.get(r, 0) + n
        for t, n in rec.counts().items():
            counts[t] = counts.get(t, 0) + n
        retries += result.retry_count; chunks += result.total_chunks; fb_chunks += result.fallback_chunks
        usage_in += result.usage.input_tokens; usage_out += result.usage.output_tokens
        per_page[d.name] = {
            "cer_src": pEs / pL, "cer_out": pE / pL, "chunks": result.total_chunks,
            "retries": result.retry_count, "fallback_chunks": result.fallback_chunks,
            "fallback_lines": result.fallback_lines, "review_lines": result.review_lines,
            "fallback_reasons": dict(result.fallback_reasons), "events": rec.counts(),
            "texts": {k: [src[k], got.get(k, src[k]), ref[k]] for k in ids},
        }
        print(
            f"  {d.name[:28]:<30} CER {pEs/pL:>6.2%} → {pE/pL:>6.2%}  chunks={result.total_chunks} "
            f"retries={result.retry_count} repli_chunks={result.fallback_chunks} "
            f"repli_lignes={result.fallback_lines} revue={result.review_lines}",
            flush=True,
        )
    summary = {
        "arm": name, "cer_src": Es / L if L else None, "cer_out": E / L if L else None,
        "changed": acc, "mis_attached": wrong, "chunks": chunks, "retries": retries,
        "fallback_chunks": fb_chunks, "fallback_reasons": fallback, "events": counts,
        "tokens_in": usage_in, "tokens_out": usage_out, "seconds": round(time.time() - t0),
        "pages": per_page,
    }
    (OUT / f"sak_run_{name.replace('·', '_').replace('()', '')}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(
        f"  ⇒ CER {summary['cer_src']:.2%} → {summary['cer_out']:.2%} | changées {acc} | "
        f"MAL R. {wrong} | chunks {chunks} | retries {retries} | repli chunks {fb_chunks} | "
        f"replis {fallback} | jetons {usage_in}+{usage_out} | {summary['seconds']} s",
        flush=True,
    )
    return summary


def _lines_from_bytes(data: bytes) -> dict[str, str]:
    return _lines_of_tree(etree.fromstring(data))


async def main() -> int:
    key = Path(os.environ["MISTRAL_KEY_FILE"]).read_text().strip()
    arms = _arms(key)
    wanted = sys.argv[1:] or list(arms)
    for name in wanted:
        await _run_arm(name, arms[name])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
