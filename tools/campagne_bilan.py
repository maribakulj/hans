"""Bilan d'une campagne : un tableau Markdown par corpus à partir des JSON de ~/corpus-vt/resultats/campagne/."""

from __future__ import annotations

import json
import sys
from pathlib import Path

OUT = Path.home() / "corpus-vt" / "resultats" / "campagne"


def main(pattern: str = "") -> None:
    rows = []
    for f in sorted(OUT.glob("*.json")):
        if f.name.startswith("undeliverable") or pattern not in f.name:
            continue
        a = json.loads(f.read_text(encoding="utf-8"))
        if a.get("partial"):
            continue
        failed = [p for p, v in a["pages"].items() if "error" in v]
        rows.append((a["corpus"], a["producer"], a.get("max_side"), a["prompt"], a["model"], a["cer_src"], a["cer_out"],
                     a["changed"], a["better"], a["worse"], a["unanchored"], a["wrong"], a["retries"], a["fb_chunks"],
                     a["tokens_in"], a["tokens_out"], a["seconds"], len(a["pages"]) - len(failed), len(failed)))
    for corpus in ("ocr17", "newseye"):
        sub = [r for r in rows if r[0] == corpus]
        if not sub:
            continue
        print(f"\n### {corpus}\n")
        print("| producteur | prompt | modèle | pages | CER source → sortie | changées | améliorées | dégradées | sans ancrage | proxy mal | retries | chunks repliés | jetons in+out | s |")
        print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in sorted(sub, key=lambda r: r[6]):
            prod = r[1] + (str(r[2]) if r[2] else "")
            pages = f"{r[17]}" + (f" (+{r[18]} échec)" if r[18] else "")
            print(f"| {prod} | {r[3]} | {r[4].replace('mistral-','').replace('-latest','')} | {pages} | {r[5]:.2%} → **{r[6]:.2%}** | {r[7]} | {r[8]} | {r[9]} | **{r[10]}** | {r[11]} | {r[12]} | {r[13]} | {r[14]//1000}k+{r[15]//1000}k | {r[16]} |")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
