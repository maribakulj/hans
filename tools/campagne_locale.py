"""Réparation locale, sans pixels, sur autant de corpus que possible.

    .venv/bin/python tools/campagne_locale.py campaigns/locale.json --strict

Cinq bras par corpus, tous aveugles aux pixels :

    ligne entière       le prorata de saknussemm AVANT la PR #167 : toutes
                        les boîtes de la ligne jetées, la largeur répartie
    locale, prorata     seule la boîte fusionnée de deux mots voisins est
                        recoupée, au prorata 1 / 0,6
    locale, apprise     idem, avec les largeurs apprises sur les boîtes de
                        la page (cross-fit par parité, jamais la ligne jugée)
    locale 3, apprise   trois mots voisins fusionnés, largeurs apprises
    saknussemm          le VRAI chemin : fichier corrompu (deux mots collés
                        dans le XML), correction, réécriture par
                        ``rewrite_alto_file`` ou ``rewrite_page_file``,
                        boîtes relues — ALTO et PAGE

Lecteurs : ALTO (``read_lines``), PAGE (``read_page_lines``), DjVu XML
d'Internet Archive (``read_djvu_lines``, 60 premières pages).

Le fichier de campagne :

    {"corpora": {"nom": {"reader": "alto", "files": ["/chemin/..."]}}}
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from hans.alto import ReferenceLine, read_djvu_lines, read_lines, read_page_lines
from hans.corrupt import MergeCase, cases_from_lines, line_cases
from hans.measure import Report, Resolver, interval_distance, score_many
from hans.resolvers import ProportionalResolver
from hans.widths import LearnedWidthResolver

READERS: dict[str, Callable[[Path], list[ReferenceLine]]] = {
    "alto": read_lines,
    "page": read_page_lines,
    "djvu": lambda p: read_djvu_lines(p, max_pages=60),
}

#: Lignes corrompues par fichier pour le bout en bout : assez pour une
#: distribution, borné pour que vingt corpus tiennent dans une session.
E2E_LINES = 200


def _local(el: etree._Element) -> str:
    return str(etree.QName(el).localname) if isinstance(el.tag, str) else ""


# ---------------------------------------------------------------------------
# bout en bout : corrompre le XML, corriger, réécrire, relire
# ---------------------------------------------------------------------------


def _glue_in_tree(root: etree._Element, case: MergeCase) -> bool:
    """Colle les deux mots de ``case`` dans l'arbre : une String, l'union."""
    for el in root.iter():
        if _local(el) != "TextLine" or el.get("ID") != case.line_id:
            continue
        strings = [c for c in el if _local(c) == "String"]
        i = case.first_index
        if i + 1 >= len(strings):
            return False
        a, b = strings[i], strings[i + 1]
        a_h = int(float(a.get("HPOS")))
        b_right = int(float(b.get("HPOS"))) + int(float(b.get("WIDTH")))
        a.set("CONTENT", case.source_content)
        a.set("WIDTH", str(b_right - a_h))
        # tout ce qui sépare a de b (SP, éventuellement HYP) disparaît avec b
        sib = a.getnext()
        while sib is not None and sib is not b:
            nxt = sib.getnext()
            el.remove(sib)
            sib = nxt
        el.remove(b)
        return True
    return False


def _e2e(
    path: Path, lines: list[ReferenceLine], cases: list[MergeCase]
) -> tuple[list[float], list[float], int, int] | None:
    """Le chemin de production de saknussemm sur un fichier corrompu.

    Une ligne sur ``len(cases) / E2E_LINES`` reçoit une fusion ; le fichier
    corrompu est réécrit avec, pour ces lignes, le texte d'origine comme
    correction, et pour les autres leur propre texte (chemin UNTOUCHED).
    """
    try:
        from saknussemm.formats.loader import (
            adapter_for_format,
            build_document_manifest,
        )
    except ImportError as exc:
        print(f"    bout en bout impossible : {exc}")
        return None
    ids = [ln.line_id for ln in lines]
    if len(set(ids)) != len(ids):
        return None
    # au plus une ligne sur quatre reçoit une fusion : en production, le
    # modèle de largeurs est ajusté sur la page telle qu'elle arrive, dont
    # les quelques lignes que le chemin lent va redessiner ; corrompre
    # toutes les lignes d'une petite page ferait porter au modèle une
    # pollution que la production ne connaît pas
    per_line: dict[str, list[MergeCase]] = {}
    for case in cases:
        per_line.setdefault(case.line_id, []).append(case)
    step = max(4, len(per_line) // E2E_LINES)
    chosen = [
        group[k % len(group)]
        for k, group in enumerate(per_line.values())
        if k % step == 0
    ][:E2E_LINES]
    if not chosen:
        return None

    tree = etree.parse(str(path))
    root = tree.getroot()
    glued = [c for c in chosen if _glue_in_tree(root, c)]
    if not glued:
        return None
    tmp = Path(__file__).resolve().parent.parent / ".e2e_tmp"
    tmp.mkdir(exist_ok=True)
    corrupted = tmp / path.name
    tree.write(str(corrupted), xml_declaration=True, encoding=tree.docinfo.encoding)

    try:
        doc = build_document_manifest([(corrupted, corrupted.name)])
        wanted = {c.line_id: c for c in glued}
        for page in doc.pages:
            for lm in page.lines:
                # the source text with the glued word split back, so that
                # hyphens and no-break spaces stay exactly as the parser
                # reconstructs them: only the segmentation changes
                lm.corrected_text = (
                    lm.ocr_text.replace(
                        wanted[lm.line_id].source_content,
                        wanted[lm.line_id].tokens[0]
                        + " "
                        + wanted[lm.line_id].tokens[2],
                        1,
                    )
                    if lm.line_id in wanted
                    else lm.ocr_text
                )
        out = adapter_for_format(doc.source_format).rewrite_file(
            corrupted, doc.pages, "hans", "campagne-locale"
        )
        result = etree.fromstring(out.xml_bytes)
    except Exception as exc:  # noqa: BLE001 -- un corpus qui casse le parseur est un résultat
        print(
            f"    bout en bout impossible sur {path.name} : {type(exc).__name__}: {exc}"
        )
        return None
    finally:
        corrupted.unlink(missing_ok=True)

    errors: list[float] = []
    normalised: list[float] = []
    failures = 0
    for el in result.iter():
        if _local(el) != "TextLine" or el.get("ID") not in wanted:
            continue
        case = wanted[el.get("ID")]
        children = [c for c in el if _local(c) in ("String", "SP")]
        strings = [c for c in children if _local(c) == "String"]
        i = case.first_index
        if i + 1 >= len(strings):
            failures += 1
            continue
        a, b = strings[i], strings[i + 1]
        between = children[children.index(a) + 1 : children.index(b)]
        sps = [c for c in between if _local(c) == "SP"]
        if len(sps) != 1:
            failures += 1
            continue
        sp = sps[0]
        mid = float(sp.get("HPOS")) + float(sp.get("WIDTH")) / 2
        start, end = case.gaps[0]
        err = interval_distance((mid, mid), (float(start), float(end)))
        errors.append(err)
        if case.mean_char_width > 0:
            normalised.append(err / case.mean_char_width)
    if not errors:
        return None
    return errors, normalised, failures, len(glued)


def _page_glue(root: etree._Element, case: MergeCase) -> bool:
    """PAGE : colle deux ``Word`` voisins — un seul élément, l'union comme polygone."""
    for el in root.iter():
        if _local(el) != "TextLine" or (el.get("id") or el.get("ID")) != case.line_id:
            continue
        words = [c for c in el if _local(c) == "Word"]
        i = case.first_index
        if i + 1 >= len(words):
            return False
        a, b = words[i], words[i + 1]

        def pts(w: etree._Element) -> list[tuple[int, int]]:
            raw = next(c.get("points") for c in w if _local(c) == "Coords")
            return [
                (int(float(x)), int(float(y)))
                for x, y in (p.split(",") for p in raw.split())
            ]

        both = pts(a) + pts(b)
        xs, ys = [p[0] for p in both], [p[1] for p in both]
        box = f"{min(xs)},{min(ys)} {max(xs)},{min(ys)} {max(xs)},{max(ys)} {min(xs)},{max(ys)}"
        next(c for c in a if _local(c) == "Coords").set("points", box)
        for te in a.iter():
            if _local(te) == "Unicode":
                te.text = case.source_content
        el.remove(b)
        # le texte de ligne suit ses mots, comme un producteur l'aurait écrit
        glued = " ".join(
            next((u.text or "" for u in w.iter() if _local(u) == "Unicode"), "")
            for w in el
            if _local(w) == "Word"
        )
        for te in el:
            if _local(te) == "TextEquiv":
                for u in te:
                    if _local(u) == "Unicode":
                        u.text = glued
        return True
    return False


def _e2e_page(
    path: Path, lines: list[ReferenceLine], cases: list[MergeCase]
) -> tuple[list[float], list[float], int, int] | None:
    """Le chemin de production de saknussemm sur un PAGE corrompu (voir ``_e2e``)."""
    try:
        from saknussemm.formats.loader import (
            adapter_for_format,
            build_document_manifest,
        )
    except ImportError:
        return None
    ids = [ln.line_id for ln in lines]
    if len(set(ids)) != len(ids):
        return None
    per_line: dict[str, list[MergeCase]] = {}
    for case in cases:
        per_line.setdefault(case.line_id, []).append(case)
    step = max(4, len(per_line) // E2E_LINES)
    chosen = [g[k % len(g)] for k, g in enumerate(per_line.values()) if k % step == 0][
        :E2E_LINES
    ]
    tree = etree.parse(str(path))
    glued = [c for c in chosen if _page_glue(tree.getroot(), c)]
    if not glued:
        return None
    tmp = Path(__file__).resolve().parent.parent / ".e2e_tmp"
    tmp.mkdir(exist_ok=True)
    corrupted = tmp / path.name
    tree.write(str(corrupted), xml_declaration=True, encoding=tree.docinfo.encoding)
    truth = {ln.line_id: ln for ln in lines}
    wanted = {c.line_id: c for c in glued}
    try:
        doc = build_document_manifest([(corrupted, corrupted.name)])
        for page in doc.pages:
            for lm in page.lines:
                if lm.line_id in wanted:
                    lm.corrected_text = " ".join(
                        w.text for w in truth[lm.line_id].words
                    )
                else:
                    lm.corrected_text = lm.ocr_text
        out = adapter_for_format(doc.source_format).rewrite_file(
            corrupted, doc.pages, "hans", "campagne-locale"
        )
        result = etree.fromstring(out.xml_bytes)
    except Exception as exc:  # noqa: BLE001
        print(
            f"    bout en bout PAGE impossible sur {path.name} : {type(exc).__name__}: {exc}"
        )
        return None
    finally:
        corrupted.unlink(missing_ok=True)
    errors: list[float] = []
    normalised: list[float] = []
    failures = 0
    for el in result.iter():
        lid = el.get("id") or el.get("ID")
        if _local(el) != "TextLine" or lid not in wanted:
            continue
        case = wanted[lid]
        words = [c for c in el if _local(c) == "Word"]
        i = case.first_index
        if i + 1 >= len(words) or len(words) != len(truth[lid].words):
            failures += 1
            continue

        def xs(w: etree._Element) -> tuple[int, int]:
            raw = next(c.get("points") for c in w if _local(c) == "Coords")
            v = [int(float(p.split(",")[0])) for p in raw.split()]
            return min(v), max(v)

        mid = (xs(words[i])[1] + xs(words[i + 1])[0]) / 2
        start, end = case.gaps[0]
        err = interval_distance((mid, mid), (float(start), float(end)))
        errors.append(err)
        if case.mean_char_width > 0:
            normalised.append(err / case.mean_char_width)
    if not errors:
        print(
            f"    PAGE {path.name} : aucune ligne reconstruite ({failures} lignes sans mots en sortie)"
        )
        return None
    return errors, normalised, failures, len(glued)


def _pool(parts: list[tuple[list[float], list[float], int, int]]) -> Report:
    errors = [e for p in parts for e in p[0]]
    normalised = [n for p in parts for n in p[1]]
    ordered = sorted(errors)
    return Report(
        resolver="saknussemm, bout en bout",
        cases=sum(p[3] for p in parts),
        boundaries=len(errors),
        failures=sum(p[2] for p in parts),
        mean=sum(errors) / len(errors),
        median=ordered[len(ordered) // 2],
        p90=ordered[min(len(ordered) - 1, int(0.9 * (len(ordered) - 1) + 0.5))],
        worst=max(errors),
        mean_chars=sum(normalised) / len(normalised) if normalised else 0.0,
        within_half_char=(
            sum(1 for e in normalised if e <= 0.5) / len(normalised)
            if normalised
            else 0.0
        ),
    )


# ---------------------------------------------------------------------------
# boîtes jointives : la frontière est un point, pas un blanc
# ---------------------------------------------------------------------------


def _tiling(lines: list[ReferenceLine]) -> bool:
    """Vrai quand le producteur colle ses boîtes bord à bord.

    Les exports DjVu d'Internet Archive (ABBYY) donnent à chaque mot une
    boîte qui inclut l'espace qui le suit : le blanc entre deux mots est
    nul dans 96-99 % des cas. Le vrai « blanc » est alors un point, et
    noter le point médian d'un SP contre ce point pénalise d'une demi-espace
    toute réponse qui dessine un SP. Pour ces corpus on note le BORD GAUCHE
    du mot suivant, qui est la seule frontière que le producteur ait écrite.
    """
    gaps = [b.hpos - a.right for ln in lines for a, b in zip(ln.words, ln.words[1:])]
    return bool(gaps) and sum(1 for g in gaps if g <= 0) > len(gaps) / 2


def _score_edges(groups: list[tuple[Resolver, list[MergeCase]]], name: str) -> Report:
    errors: list[float] = []
    normalised: list[float] = []
    failures = cases = 0
    for resolver, case_list in groups:
        for case in case_list:
            cases += 1
            try:
                boxes = resolver.resolve(case.request())
            except Exception:  # noqa: BLE001
                failures += 1
                continue
            words = [b for b in boxes if not b.text.isspace()]
            for k, true_word in enumerate(case.true_boxes[1:], start=1):
                err = abs(words[k].hpos - true_word.hpos)
                errors.append(err)
                if case.mean_char_width > 0:
                    normalised.append(err / case.mean_char_width)
    if not errors:
        return Report(name, cases, 0, failures, 0, 0, 0, 0, 0, 0)
    ordered = sorted(errors)
    return Report(
        resolver=name,
        cases=cases,
        boundaries=len(errors),
        failures=failures,
        mean=sum(errors) / len(errors),
        median=ordered[len(ordered) // 2],
        p90=ordered[min(len(ordered) - 1, int(0.9 * (len(ordered) - 1) + 0.5))],
        worst=max(errors),
        mean_chars=sum(normalised) / len(normalised),
        within_half_char=sum(1 for e in normalised if e <= 0.5) / len(normalised),
    )


# ---------------------------------------------------------------------------


def _row(name: str, r: Report | None) -> str:
    if r is None:
        return f"| {name} | — | — | — | — | — |"
    return (
        f"| {name} | {r.boundaries} | {r.within_half_char:.1%} | "
        f"{r.mean_chars:.3f} | {r.p90:.1f} | {r.worst:.1f} |"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="campagne_locale")
    parser.add_argument("config", type=Path)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", type=Path, default=None, help="résultats bruts")
    args = parser.parse_args(argv)

    if args.strict:
        try:
            import saknussemm.formats.alto.rewriter  # noqa: F401
        except ImportError:
            print("refus de mesurer : saknussemm absent (parité non épinglée)")
            return 2

    spec = json.loads(args.config.read_text(encoding="utf-8"))
    results: dict[str, dict[str, dict[str, float] | None]] = {}
    for name, entry in spec["corpora"].items():
        reader = READERS[entry.get("reader", "alto")]
        files = [Path(f).expanduser() for f in entry["files"]]
        arms: dict[str, list[tuple[Resolver, list[MergeCase]]]] = {
            "ligne entière": [],
            "locale, prorata": [],
            "locale, apprise": [],
            "locale 3, apprise": [],
        }
        e2e_parts: list[tuple[list[float], list[float], int, int]] = []
        n_lines = 0
        tiling = False
        for f in files:
            if not f.exists():
                print(f"    absent : {f}")
                continue
            try:
                lines = reader(f)
            except Exception as exc:  # noqa: BLE001
                print(f"    illisible : {f.name} ({type(exc).__name__})")
                continue
            whole = line_cases(lines)
            two = cases_from_lines(lines, run=2)
            three = cases_from_lines(lines, run=3)
            if not two:
                continue
            n_lines += len(lines)
            tiling = tiling or _tiling(lines)
            try:
                learned = LearnedWidthResolver(lines)
            except ValueError:
                continue
            arms["ligne entière"].append((ProportionalResolver(), whole))
            arms["locale, prorata"].append((ProportionalResolver(), two))
            arms["locale, apprise"].append((learned, two))
            arms["locale 3, apprise"].append((learned, three))
            kind = entry.get("reader", "alto")
            part = (
                _e2e(f, lines, two)
                if kind == "alto"
                else _e2e_page(f, lines, two)
                if kind == "page"
                else None
            )
            if part is not None:
                e2e_parts.append(part)
        if not arms["locale, prorata"]:
            print(f"\n### {name} : rien à mesurer")
            continue
        tag = (
            " — boîtes jointives, mesure au bord gauche du mot suivant"
            if tiling
            else ""
        )
        print(f"\n### {name} — {n_lines} lignes, {len(files)} fichier(s){tag}")
        print(
            "| bras | frontières | ≤ 0,5 car. | moyenne (car.) | p90 (px) | pire (px) |"
        )
        print("|---|---|---|---|---|---|")
        results[name] = {}
        for arm, groups in arms.items():
            r = _score_edges(groups, arm) if tiling else score_many(groups, arm)
            print(_row(arm, r))
            results[name][arm] = r.__dict__
        if e2e_parts:
            pooled = _pool(e2e_parts)
            print(_row("saknussemm, vrai rewriter (bout en bout)", pooled))
            results[name]["saknussemm"] = pooled.__dict__
        else:
            print(_row("saknussemm, vrai rewriter (bout en bout)", None))
    if args.json:
        args.json.write_text(json.dumps(results, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
