"""H4 : linéariser une page en un bloc, corriger en un appel, reprojeter.

    MISTRAL_KEY_FILE=<clé> python tools/block_roundtrip.py <alto.xml> <sortie.json>

Le modèle ne reçoit aucune structure : du texte continu, mots coupés
recollés, et il rend du texte continu. Les lignes sont reconstituées ici, par
alignement déterministe — sans pixels : `core/alignment.py` de saknussemm
ferait le même travail.

Deux pièges appris en l'écrivant, tous deux silencieux :

- le trait d'union d'une césure vit dans un élément ``<HYP>``, PAS dans le
  ``CONTENT`` du ``String``. Le chercher en fin de texte n'en trouve que 13
  sur 115, laisse autant de lignes finir au milieu d'un mot, et le correcteur
  ajoute alors lui-même le tiret manquant ;
- recoller un mot coupé OBLIGE à le recouper à la re-projection. Sans ça sa
  seconde moitié disparaît de la ligne suivante, et la page perd du texte
  sans que rien ne le signale.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from hans.alto import read_lines  # noqa: E402

HYPHENS = "-¬‐‑­"

SYSTEM = (
    "Tu es un moteur de correction post-OCR pour documents patrimoniaux.\n"
    "Corrige uniquement les erreurs manifestes d'OCR. Conserve la langue, "
    "l'orthographe historique intentionnelle, la ponctuation d'origine.\n"
    "Ne traduis pas, ne modernise pas, ne resume pas, n'ajoute ni ne supprime "
    "de phrase.\n"
    "Rends UNIQUEMENT le texte corrige, une ligne de sortie par ligne recue, "
    "dans le meme ordre."
)


def all_lines(alto: Path):
    """TOUTES les TextLine du document, pas seulement les mesurables.

    ``hans.alto.read_lines`` écarte les lignes sans géométrie complète ou de
    moins de deux mots — 538 sur 566 ici. C'est ce qu'il faut pour NOTER une
    géométrie, et c'est faux pour linéariser : deux entrées consécutives ne
    sont alors plus voisines dans le document, et la queue d'un mot coupé
    atterrit sur une ligne écartée. Mesuré : 8 lignes reçoivent le texte de
    leur voisine, et la fidélité tombe à 96,7 % au lieu de 100 %.
    """
    from lxml import etree

    out = []
    for el in etree.parse(str(alto)).iter():
        if not isinstance(el.tag, str) or etree.QName(el).localname != "TextLine":
            continue
        words = [
            c.get("CONTENT")
            for c in el
            if isinstance(c.tag, str)
            and etree.QName(c).localname == "String"
            and c.get("CONTENT")
        ]
        out.append((el.get("ID") or f"line-{len(out)}", " ".join(words)))
    return out


def hyphenated_ids(alto: Path) -> set[str]:
    """Les lignes que l'ALTO marque comme coupées, via leur élément <HYP>."""
    from lxml import etree

    out = set()
    for el in etree.parse(str(alto)).iter():
        if not isinstance(el.tag, str) or etree.QName(el).localname != "TextLine":
            continue
        if any(
            isinstance(c.tag, str) and etree.QName(c).localname == "HYP" for c in el
        ):
            if el.get("ID"):
                out.add(el.get("ID"))
    return out


def linearise(lines, hyphen_ids: frozenset[str] | set[str] = frozenset()):
    """``(bloc, index, owners)``.

    ``owners`` donne, pour chaque mot du bloc, la ligne d'où il vient — et,
    pour un mot recollé, les deux lignes et les deux fragments d'origine.
    C'est ce qui permettra de le recouper.
    """
    index = (
        lines
        if lines and isinstance(lines[0], tuple)
        else [(ln.line_id, " ".join(w.text for w in ln.words)) for ln in lines]
    )

    block_lines: list[str] = []
    owners: list[dict] = []
    carry: tuple[str, str, str] | None = None  # (fragment, ligne, tiret visible)

    for i, (lid, txt) in enumerate(index):
        cur = txt
        pending: dict | None = None
        if carry is not None:
            head, head_line, head_suffix = carry
            tail, _, rest = cur.partition(" ")
            pending = {
                "word": head + tail, "line": head_line,
                "tail_line": lid, "head": head, "tail": tail,
                "head_suffix": head_suffix,
            }
            cur = rest
            carry = None

        is_cut = lid in hyphen_ids or cur.rstrip().endswith(tuple(HYPHENS))
        words = cur.split()
        if is_cut and i + 1 < len(index) and words:
            raw = words.pop()
            last = raw.rstrip(HYPHENS)
            # Le tiret VISIBLE dans le CONTENT fait partie du texte de la
            # ligne ; celui d'un element <HYP> n'y est pas. Le premier doit
            # revenir au recoupage, le second non — sinon le controle a vide
            # echoue sur 13 lignes et on croit a un defaut de re-projection.
            carry = (last, lid, raw[len(last):])

        emitted = ([pending] if pending else []) + [
            {"word": w, "line": lid} for w in words
        ]
        if emitted:
            owners.extend(emitted)
            block_lines.append(" ".join(o["word"] for o in emitted))

    if carry is not None:
        owners.append({"word": carry[0], "line": carry[1]})
        block_lines.append(carry[0])

    return "\n".join(block_lines), index, owners


def correct(block: str, model: str, key: str) -> tuple[str, dict]:
    body = json.dumps(
        {
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": block},
            ],
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.mistral.ai/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=900) as r:
        d = json.loads(r.read())
    return d["choices"][0]["message"]["content"], d.get("usage", {})


def _resplit(joined: str, owner: dict) -> tuple[str, str]:
    """Recouper un mot recollé là où la césure le coupait.

    La frontière est cherchée dans le mot CORRIGÉ en alignant celui-ci sur
    les deux fragments d'origine : une correction qui change la longueur du
    mot déplacerait sinon la coupe.
    """
    head, tail = owner["head"], owner["tail"]
    sm = SequenceMatcher(None, head + tail, joined, autojunk=False)
    boundary = len(head)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if i1 <= boundary <= i2:
            offset = min(boundary - i1, j2 - j1)
            boundary = j1 + offset
            break
    else:
        boundary = min(len(head), len(joined))
    return joined[:boundary] + owner.get("head_suffix", ""), joined[boundary:]


def reproject(corrected: str, index, owners) -> dict[str, str]:
    """Rendre à chaque ligne son texte, par alignement de mots."""
    src = [o["word"] for o in owners]
    tgt = corrected.split()
    out: dict[str, list[str]] = {lid: [] for lid, _ in index}

    def place(word: str, k: int) -> None:
        o = owners[k] if k < len(owners) else owners[-1]
        if "tail_line" in o:
            a, b = _resplit(word, o)
            if a:
                out[o["line"]].append(a)
            if b:
                out[o["tail_line"]].append(b)
        else:
            out[o["line"]].append(word)

    for tag, i1, i2, j1, j2 in SequenceMatcher(
        None, src, tgt, autojunk=False
    ).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                place(tgt[j1 + k], i1 + k)
        elif tag in ("replace", "insert"):
            for k, w in enumerate(tgt[j1:j2]):
                place(w, min(i1 + k, max(i1, i2 - 1)))
    return {lid: " ".join(ws) for lid, ws in out.items()}


def main() -> int:
    alto, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    model = sys.argv[3] if len(sys.argv) > 3 else "mistral-small-latest"
    key = Path(os.environ["MISTRAL_KEY_FILE"]).read_text().strip()

    lines = all_lines(alto)
    block, index, owners = linearise(lines, hyphenated_ids(alto))
    joins = sum(1 for o in owners if "tail_line" in o)
    print(
        f"{len(lines)} lignes -> bloc de {len(block)} car., "
        f"{joins} césures recollées",
        flush=True,
    )
    corrected, usage = correct(block, model, key)
    print(f"usage: {usage}", flush=True)
    proj = reproject(corrected, index, owners)
    out_path.write_text(
        json.dumps(
            {
                "model": model, "usage": usage, "joins": joins,
                "source": dict(index), "projected": proj,
                "block_in": block, "block_out": corrected,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"-> {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
