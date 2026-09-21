"""H4 : linéariser une page en un bloc, corriger en un appel, reprojeter.

    python tools/block_roundtrip.py <alto.xml> <sortie.json>

Ne demande au modèle aucune structure : il reçoit du texte continu, mots
coupés recollés, et rend du texte continu. Les lignes sont reconstituées ici,
par alignement déterministe sur le bloc source.
"""
from __future__ import annotations
import json, os, sys, urllib.request
from difflib import SequenceMatcher
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from hans.alto import read_lines  # noqa: E402

SYSTEM = (
    "Tu es un moteur de correction post-OCR pour documents patrimoniaux.\n"
    "Corrige uniquement les erreurs manifestes d'OCR. Conserve la langue, "
    "l'orthographe historique intentionnelle, la ponctuation d'origine.\n"
    "Ne traduis pas, ne modernise pas, ne resume pas, n'ajoute ni ne supprime "
    "de phrase.\n"
    "Rends UNIQUEMENT le texte corrige, un paragraphe par paragraphe recu, "
    "dans le meme ordre."
)

def hyphenated_ids(alto: Path) -> set[str]:
    """Les lignes que l'ALTO marque comme coupées, via leur element <HYP>.

    Indispensable, et appris à la dure : le trait d'union d'une césure vit
    dans un element <HYP> propre, PAS dans le CONTENT du String. Chercher un
    tiret en fin de texte n'en trouve que 13 sur 115, laisse 102 lignes se
    terminer au milieu d'un mot, et le correcteur ajoute alors lui-même le
    tiret qui manque — ce qui se lit comme un échec de re-projection alors
    que c'est un bloc mal préparé.
    """
    from lxml import etree

    out = set()
    for el in etree.parse(str(alto)).iter():
        if not isinstance(el.tag, str) or etree.QName(el).localname != "TextLine":
            continue
        if any(
            isinstance(c.tag, str) and etree.QName(c).localname == "HYP" for c in el
        ):
            lid = el.get("ID")
            if lid:
                out.add(lid)
    return out


def linearise(lines, hyphen_ids=frozenset()):
    """Un mot par ligne source, césures recollées. Retourne (bloc, index)."""
    parts, index = [], []
    for ln in lines:
        txt = " ".join(w.text for w in ln.words)
        index.append((ln.line_id, txt))
        parts.append(txt)
    # recoller : une ligne finissant par un trait d'union se soude a la suivante
    block, joins = [], []
    i = 0
    while i < len(parts):
        cur = parts[i]
        if cur.endswith(("-", "¬", "‐", "‑")) and i + 1 < len(parts):
            nxt = parts[i + 1]
            head = nxt.split(" ", 1)[0]
            block.append(cur + head)
            rest = nxt.split(" ", 1)[1] if " " in nxt else ""
            joins.append(i)
            parts[i + 1] = rest
            i += 1
            if rest:
                continue
            i += 1
            continue
        block.append(cur)
        i += 1
    return "\n".join(p for p in block if p), index, joins

def correct(block: str, model: str, key: str) -> tuple[str, dict]:
    body = json.dumps({
        "model": model, "temperature": 0,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": block}],
    }).encode()
    req = urllib.request.Request(
        "https://api.mistral.ai/v1/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.loads(r.read())
    return d["choices"][0]["message"]["content"], d.get("usage", {})

def reproject(corrected: str, index) -> dict[str, str]:
    """Rendre chaque ligne son texte, par alignement de MOTS sur le bloc source."""
    src_words, owner = [], []
    for lid, txt in index:
        for w in txt.split():
            src_words.append(w); owner.append(lid)
    tgt_words = corrected.split()
    out: dict[str, list[str]] = {lid: [] for lid, _ in index}
    sm = SequenceMatcher(None, src_words, tgt_words, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                out[owner[i1 + k]].append(tgt_words[j1 + k])
        elif tag in ("replace", "insert"):
            # attribuer le bloc cible a la ligne du premier mot source couvert
            lid = owner[i1] if i1 < len(owner) else owner[-1]
            for w in tgt_words[j1:j2]:
                out[lid].append(w)
    return {lid: " ".join(ws) for lid, ws in out.items()}

def main() -> int:
    alto, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    model = sys.argv[3] if len(sys.argv) > 3 else "mistral-small-latest"
    key = Path(os.environ["MISTRAL_KEY_FILE"]).read_text().strip()
    lines = read_lines(alto)
    block, index, joins = linearise(lines, hyphenated_ids(alto))
    print(f"{len(lines)} lignes -> bloc de {len(block)} car., {len(joins)} césures recollées", flush=True)
    corrected, usage = correct(block, model, key)
    print(f"usage: {usage}", flush=True)
    proj = reproject(corrected, index)
    out_path.write_text(json.dumps({
        "model": model, "usage": usage, "joins": len(joins),
        "source": {lid: txt for lid, txt in index}, "projected": proj,
        "block_in": block, "block_out": corrected,
    }, ensure_ascii=False), encoding="utf-8")
    print(f"-> {out_path}", flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
