# Éligibilité d'un corpus à la post-correction — état au 23 septembre 2026

Ce que les mesures de H10 à H15 permettent de dire sur *quels documents*
le pipeline (image + identifiants portés + veto, puis CTC pour les boîtes)
peut traiter en production, et lesquels non.

## Les critères, dans l'ordre où ils éliminent

1. **Structure 1:1** — chaque ligne de l'ALTO est une ligne physique. La
   post-correction n'agit que sur ces lignes-là (H13 §2.9 : sur les
   fusions et les morceaux, elle polit des fragments faux). Mise en page
   simple ; pas de colonnes aspirées ni d'encarts.
2. **Texte entre ~2 % et ~50 % d'erreur par ligne** (H13 §2.8, à
   segmentation juste). En dessous de 2 %, la correction fait un peu plus
   de mal que de bien. Au-dessus de 50 %, le texte ne prouve plus rien :
   c'est de l'OCR.
3. **Une image que le VLM lit mieux que l'OCR d'origine.** Imprimé ancien
   (s long, ligatures, orthographe) : le VLM gagne beaucoup (OCR17+ :
   8,5 → 4,6 %). Petit corps du XXe : il est un lecteur médiocre (NewsEye
   : 10 % seul) et le gain fond.
4. **Français, caractères latins** — le domaine des modèles disponibles.

Le seuil de segmentation n'est mesuré qu'aux extrêmes : elle tient à ~5 %
de CER page (94–98 % de lignes retrouvées), elle lâche à ~25 % (35–54 %).
Entre les deux, pas de point (H13 §2.7).

## Corpus Gallica

| corpus | structure | texte | verdict |
|---|---|---|---|
| **Monographies XVIe–XVIIIe** | une colonne, régulière | OCR souvent mauvais | **cœur de cible** — c'est OCR17+ |
| Théâtre, poésie XVIIe–XVIIIe | idem, noms répétés | idem | passe ; exemption des jumelles utile |
| Monographies XIXe | simple | souvent 97–99 % | passe, gain faible ; trier par qualité déclarée |
| Revues savantes, bulletins (1–2 col.) | généralement 1:1 | moyen | passe **après triage géométrique** |
| Presse quotidienne 5–6 colonnes | variable | moyen, petit corps | page par page ; gain limité |
| Presse illustrée, magazines, encarts | non | — | **non** : resegmentation |
| Tableaux, partitions, cartes, manuscrits | — | — | hors périmètre |

## Trier sans vérité terrain

- **Texte** : le taux de reconnaissance OCR que Gallica publie par
  document (`NQAMOYEN` dans le METS). Viser ~70–95 %.
- **Structure**, calculable sur l'ALTO seul : blocs par page, largeur des
  lignes contre la largeur de page et des colonnes, hauteurs de lignes
  anormales, ordre incohérent, encre hors de toute boîte
  (`tools/ink_gaps.py`). *Le Temps* (H13 §2 addendum) : 0,1 % d'inversions,
  aucune ligne plus large qu'une colonne — une page qui passe.

## Ce qui n'est pas mesuré

- Le pipeline sur **l'OCR de production de Gallica** lui-même. OCR17+ est
  sur Gallica (arks dans les noms de fichiers) mais son OCR source est
  celui du projet. Tentative du 23/09 : Gallica a répondu 429 puis a
  coupé la connexion. À reprendre lentement.
- Les dégâts de segmentation propres à Gallica (colonnes aspirées,
  encarts) : aucun exemplaire avec VT en main.
- Le seuil de segmentation entre 6 et 24 % de CER page : le jeu
  d'entraînement NewsEye (127 pages) permettrait de tracer la courbe.
