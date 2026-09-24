"""Trier une page AVANT tout appel de modèle : corrigeable, ou à ré-OCRiser ?

La seule façon dont une ligne a jamais reçu le texte d'une autre, dans tout
ce que ce dépôt a mesuré (H12, H13, H17), c'est quand cette autre ligne
**n'existait pas dans l'OCR** — ratée, ou fondue dans une voisine. La marge
de saknussemm compare une proposition à toutes les sources de la page ; une
source absente n'y est pas. Le triage écarte donc les pages où la
segmentation a lâché, et il le fait sur le fichier seul (plus l'image
quand elle est là), sans vérité terrain et sans modèle.

Cinq signaux, chacun avec ce qu'il attrape :

``fused``
    part des lignes dont la hauteur dépasse ``fused_ratio`` fois la hauteur
    médiane de la page — deux lignes physiques dans une boîte.
``wide``
    part des lignes plus larges que ``wide_ratio`` fois la largeur de
    colonne estimée — une colonne aspirée dans sa voisine, un encart fondu.
``disorder``
    part des transitions de ligne qui remontent dans la même colonne — un
    ordre de lecture qui ne suit ni les colonnes ni la page.
``gaps``
    part des transitions dans la même colonne qui sautent plus de trois pas
    de ligne — des lignes que l'OCR n'a pas produites (ou des blancs de mise
    en page, d'où le seuil large).
``uncovered``
    (avec l'image) part de l'encre de la page qui ne tombe dans aucune boîte
    de ligne. Calculé pour information, jamais dans le verdict : sur une
    page illustrée, les photos sont de l'encre hors boîte.

Les seuils par défaut ont été posés sur dix-huit pages connues (H18) : les
deux pages NewsEye où Tesseract rate un tiers des lignes doivent être
refusées ; les six pages propres de 1937, *Le Temps* 1890 et neuf pages
OCR17+ acceptées. Ils sont **réglés après avoir vu ces pages**, et valent
ce que vaut un réglage sur dix-huit pages : à confirmer sur un corpus
jamais regardé avant d'en faire une règle de production.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from statistics import median

from lxml import etree


@dataclass(frozen=True)
class LineBox:
    line_id: str
    hpos: int
    vpos: int
    width: int
    height: int
    text: str

    @property
    def right(self) -> int:
        return self.hpos + self.width

    @property
    def bottom(self) -> int:
        return self.vpos + self.height


@dataclass(frozen=True)
class PageBoxes:
    width: int
    height: int
    lines: tuple[LineBox, ...]


def _local(el: etree._Element) -> str:
    return str(etree.QName(el).localname)


def _polygon_box(points: str) -> tuple[int, int, int, int]:
    xs = [int(float(p.split(",")[0])) for p in points.split()]
    ys = [int(float(p.split(",")[1])) for p in points.split()]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def read_boxes(path: Path | str) -> PageBoxes:
    """Les boîtes de lignes d'un ALTO ou d'un PAGE, par nom local, sans
    dépendre du parseur de saknussemm (le banc ne partage pas de code avec
    ce qu'il mesure)."""
    tree = etree.parse(str(path))
    width = height = 0
    lines: list[LineBox] = []
    for el in tree.iter():
        if not isinstance(el.tag, str):
            continue
        name = _local(el)
        if name == "Page":
            width = int(float(el.get("WIDTH") or el.get("imageWidth") or 0))
            height = int(float(el.get("HEIGHT") or el.get("imageHeight") or 0))
        elif name == "TextLine":
            if el.get("HPOS") is not None:
                x, y, w, h = (
                    int(float(el.get(k) or 0))
                    for k in ("HPOS", "VPOS", "WIDTH", "HEIGHT")
                )
                words = [
                    c.get("CONTENT")
                    for c in el
                    if isinstance(c.tag, str)
                    and _local(c) == "String"
                    and c.get("CONTENT")
                ]
                text = " ".join(w for w in words if w)
            else:
                coords = el.find("{*}Coords")
                if coords is None or not coords.get("points"):
                    continue
                x, y, w, h = _polygon_box(coords.get("points") or "")
                uni = el.find("{*}TextEquiv/{*}Unicode")
                text = (uni.text or "").strip() if uni is not None else ""
            if w > 0 and h > 0:
                lines.append(
                    LineBox(
                        el.get("ID") or el.get("id") or f"l{len(lines)}",
                        x,
                        y,
                        w,
                        h,
                        text,
                    )
                )
    return PageBoxes(width=width, height=height, lines=tuple(lines))


def column_width(
    page: PageBoxes,
    *,
    gap_ratio: float = 0.06,
    min_lines: int = 8,
    wide_ratio: float = 1.35,
) -> int:
    """La largeur de colonne estimée : les bords gauches se groupent par
    colonne (un saut de plus de ``gap_ratio`` × la largeur de page ouvre une
    nouvelle colonne) ; la largeur est la médiane des lignes des colonnes
    peuplées. Une page à une colonne rend la médiane de toutes ses lignes."""
    if not page.lines:
        return 0
    xs = sorted(ln.hpos for ln in page.lines)
    groups: list[list[int]] = [[xs[0]]]
    for x in xs[1:]:
        if x - groups[-1][-1] > gap_ratio * max(1, page.width):
            groups.append([x])
        else:
            groups[-1].append(x)
    populated = [g for g in groups if len(g) >= min_lines] or groups
    block = max(ln.right for ln in page.lines) - min(ln.hpos for ln in page.lines)
    starts = sorted(g[0] for g in populated)
    if len(starts) >= 2:
        spacing = int(median(b - a for a, b in pairwise(starts)))
        # Des colonnes dont la MÉDIANE des lignes déborde ne sont pas des
        # colonnes : un dialogue de théâtre indente ses répliques sous les
        # noms de personnages, et ce retrait ouvrait un second groupe de
        # bords gauches — mesuré, Bruyère et Molière étaient refusés pour
        # 59 et 67 % de lignes « trop larges ». L'estimation est alors
        # fausse, pas les lignes : la page est à une colonne.
        member = {x for g in populated for x in g}
        widths = [ln.right - ln.hpos for ln in page.lines if ln.hpos in member]
        if median(widths) <= wide_ratio * spacing:
            return spacing
    # Une seule colonne : sa largeur est celle du bloc de texte, pas la
    # médiane des lignes — au théâtre, un nom de personnage seul sur sa
    # ligne ferait passer chaque vers pour une ligne « trop large ».
    return block


def vertical_overlap(a: LineBox, b: LineBox) -> float:
    """La part de la hauteur de ``a`` recouverte par ``b``, quand les deux
    boîtes se recouvrent horizontalement d'au moins la moitié de la plus
    étroite (même colonne) ; 0 sinon."""
    hx = min(a.right, b.right) - max(a.hpos, b.hpos)
    if hx <= 0 or hx < 0.5 * min(a.width, b.width):
        return 0.0
    hy = min(a.bottom, b.bottom) - max(a.vpos, b.vpos)
    return max(0.0, hy / max(1, a.height))


def lines_to_resegment(
    page: PageBoxes, *, max_overlap: float = 0.35, fused_ratio: float | None = None
) -> dict[str, str]:
    """Le tri PAR LIGNE (VR-13) : les boîtes qui mordent sur une voisine de
    la même colonne de plus de ``max_overlap`` de leur hauteur, et, si
    ``fused_ratio`` est donné, celles plus hautes que ``fused_ratio`` fois
    la hauteur médiane de la page. Rend ``{line_id: raison}``.

    Mesuré sur NewsEye (H19, addendum) : à 0,35, 79 % des boîtes que le
    proxy dit fusionnées sont écartées, pour 8 % des lignes 1:1 — qui
    mordent aussi. Ces lignes ne sont pas à corriger : leur recadrage
    montre un bout d'une autre ligne, et le contrat « une ligne de texte
    par boîte » n'a pas de réponse juste pour elles. À re-segmenter."""
    out: dict[str, str] = {}
    med = median(ln.height for ln in page.lines) if page.lines else 0
    for ln in page.lines:
        best = max(
            (vertical_overlap(ln, o) for o in page.lines if o is not ln), default=0.0
        )
        if best > max_overlap:
            out[ln.line_id] = f"recouvre une voisine à {best:.0%}"
        elif fused_ratio is not None and med and ln.height > fused_ratio * med:
            out[ln.line_id] = f"hauteur {ln.height / med:.1f} × la médiane"
    return out


@dataclass(frozen=True)
class Thresholds:
    fused_ratio: float = 2.2
    max_fused: float = 0.05
    wide_ratio: float = 1.35
    max_wide: float = 0.05
    max_disorder: float = 0.10
    max_gaps: float = 0.10
    #: L'encre hors boîte n'entre PAS dans le verdict : sur une page
    #: illustrée, les photos et les filets sont de l'encre hors de toute
    #: boîte de ligne (35 à 87 % sur les hebdomadaires de 1937), et le
    #: signal ne dit plus rien des lignes ratées. Il est calculé et rendu
    #: quand l'image est là, pour information.
    max_uncovered: float | None = None


DEFAULT_THRESHOLDS = Thresholds()


@dataclass
class Verdict:
    accepted: bool
    fused: float
    wide: float
    disorder: float
    gaps: float
    uncovered: float | None
    column_width: int
    lines: int
    reasons: list[str] = field(default_factory=list)


def _disorder(page: PageBoxes, col_w: int) -> float:
    """Part des transitions qui REMONTENT dans la même colonne. Un passage à
    la colonne suivante remonte légitimement ; un retour en arrière de
    colonne ou une remontée dans la colonne courante ne suit aucun ordre."""
    if len(page.lines) < 2 or col_w <= 0:
        return 0.0
    left = min(ln.hpos for ln in page.lines)

    def col(ln: LineBox) -> int:
        return int((ln.hpos + ln.width / 2 - left) / col_w)

    bad = 0
    for a, b in pairwise(page.lines):
        if (col(b) == col(a) and b.vpos < a.vpos - a.height) or col(b) < col(a):
            bad += 1
    return bad / (len(page.lines) - 1)


def _gaps(page: PageBoxes, col_w: int, *, ratio: float = 3.0) -> float:
    """Part des transitions dans la même colonne dont le saut vertical
    dépasse ``ratio`` fois le pas de ligne médian de la page — des lignes
    que l'OCR n'a pas produites, ou des blancs de mise en page. Sans image,
    c'est le seul témoin des lignes ratées ; il compte aussi les photos et
    les titres, d'où son seuil large."""
    if len(page.lines) < 3 or col_w <= 0:
        return 0.0
    left = min(ln.hpos for ln in page.lines)

    def col(ln: LineBox) -> int:
        return int((ln.hpos + ln.width / 2 - left) / col_w)

    pitches = [
        b.vpos - a.vpos
        for a, b in pairwise(page.lines)
        if col(a) == col(b) and b.vpos > a.vpos
    ]
    if not pitches:
        return 0.0
    pitch = median(pitches)
    big = sum(1 for d in pitches if d > ratio * pitch)
    return big / len(pitches)


def uncovered_ink(
    page: PageBoxes, image: Path | str, *, target_width: int = 1500
) -> float:
    """La part de l'encre de la page qui ne tombe dans aucune boîte de
    ligne. Otsu sur une réduction de l'image ; les boîtes sont élargies de
    10 % pour ne pas compter les marges d'encre d'une boîte juste."""
    from PIL import Image, ImageDraw, ImageOps  # import paresseux

    Image.MAX_IMAGE_PIXELS = None
    with Image.open(image) as raw:
        im = ImageOps.exif_transpose(raw).convert("L")
        scale = min(1.0, target_width / max(1, im.width))
        if scale < 1.0:
            im = im.resize(
                (max(1, int(im.width * scale)), max(1, int(im.height * scale)))
            )
    hist = im.histogram()
    total = sum(hist)
    # Otsu
    best_t, best_v = 128, -1.0
    sum_all = sum(i * c for i, c in enumerate(hist))
    w0 = s0 = 0.0
    for t in range(256):
        w0 += hist[t]
        if w0 == 0:
            continue
        w1 = total - w0
        if w1 == 0:
            break
        s0 += t * hist[t]
        m0, m1 = s0 / w0, (sum_all - s0) / w1
        v = w0 * w1 * (m0 - m1) ** 2
        if v > best_v:
            best_v, best_t = v, t
    ink = im.point(lambda p: 255 if p < best_t else 0)
    sx = im.width / max(1, page.width or im.width)
    sy = im.height / max(1, page.height or im.height)
    mask = Image.new("L", im.size, 0)
    draw = ImageDraw.Draw(mask)
    for ln in page.lines:
        mx, my = ln.width * 0.10, ln.height * 0.10
        draw.rectangle(
            (
                (ln.hpos - mx) * sx,
                (ln.vpos - my) * sy,
                (ln.right + mx) * sx,
                (ln.bottom + my) * sy,
            ),
            fill=255,
        )
    from PIL import ImageChops

    outside = ImageChops.subtract(ink, mask)
    ink_px = ink.histogram()[255]
    return outside.histogram()[255] / ink_px if ink_px else 0.0


def triage(
    path: Path | str,
    image: Path | str | None = None,
    *,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> Verdict:
    """Le verdict d'une page, avec ses raisons et ses nombres."""
    page = read_boxes(path)
    if len(page.lines) < 2:
        return Verdict(
            False, 0, 0, 0, 0, None, 0, len(page.lines), ["moins de deux lignes"]
        )
    col_w = column_width(page, wide_ratio=thresholds.wide_ratio)
    med_h = median(ln.height for ln in page.lines)
    fused = sum(
        1 for ln in page.lines if ln.height > thresholds.fused_ratio * med_h
    ) / len(page.lines)
    wide = (
        sum(1 for ln in page.lines if ln.width > thresholds.wide_ratio * col_w)
        / len(page.lines)
        if col_w
        else 0.0
    )
    disorder = _disorder(page, col_w)
    gaps = _gaps(page, col_w)
    uncovered = uncovered_ink(page, image) if image is not None else None
    reasons = []
    if fused > thresholds.max_fused:
        reasons.append(
            f"{fused:.0%} de lignes plus hautes que {thresholds.fused_ratio}× la médiane"
        )
    if wide > thresholds.max_wide:
        reasons.append(
            f"{wide:.0%} de lignes plus larges que {thresholds.wide_ratio} colonne"
        )
    if disorder > thresholds.max_disorder:
        reasons.append(f"{disorder:.0%} de transitions à rebours")
    if gaps > thresholds.max_gaps:
        reasons.append(f"{gaps:.0%} de sauts verticaux de plus de 3 pas de ligne")
    if (
        uncovered is not None
        and thresholds.max_uncovered is not None
        and uncovered > thresholds.max_uncovered
    ):
        reasons.append(f"{uncovered:.0%} de l'encre hors de toute boîte")
    return Verdict(
        accepted=not reasons,
        fused=fused,
        wide=wide,
        disorder=disorder,
        gaps=gaps,
        uncovered=uncovered,
        column_width=col_w,
        lines=len(page.lines),
        reasons=reasons,
    )


__all__ = [
    "DEFAULT_THRESHOLDS",
    "LineBox",
    "PageBoxes",
    "Thresholds",
    "Verdict",
    "column_width",
    "lines_to_resegment",
    "read_boxes",
    "triage",
    "uncovered_ink",
    "vertical_overlap",
]
