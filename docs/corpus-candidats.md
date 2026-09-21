# Corpus candidats — vérifiés et écartés

Relevé du 2026-09-21. **Vérifié empiriquement** veut dire : téléchargé, lu
par `hans.alto`, échelle image/ALTO mesurée, langue constatée. Les
descriptions publiées ne suffisent pas — voir Reichsanzeiger plus bas.

## Le critère qui élimine presque tout

Le banc a besoin de **boîtes au mot** comme vérité terrain. Or la plupart des
corpus GT de HTR sont annotés à la **ligne** : les boîtes au mot viennent des
moteurs OCR, pas des campagnes d'annotation humaine. Il faut donc viser les
**ALTO de bibliothèques numérisées**, pas les jeux de données HTR.

## ✅ Vérifié et prêt — BnL Open Data, *STARTER PACK*

- <https://data.bnl.lu/open-data/digitization/newspapers/set04-5days.zip>
- 250 Mo, **CC0**, 5 numéros, 22 pages, journaux luxembourgeois de 1868.
- ALTO avec `String`/`HPOS`/`WIDTH`/`WC`/`CC`, images **TIFF** pleine
  résolution, plus METS et PDF.
- **2 208 lignes exploitables, 2 207 cas ligne-entière** — du même ordre que
  les trois corpus de H1.
- **Échelle mesurée : 1,1809 à 1,1812 sur les 22 pages**, soit `300/254` —
  la même convention en dixièmes de millimètre que `37-GT-BNL`. Le garde de
  `tools/decode_lines.py` l'attrape et exige `--scale 1.1811`.
- **Massivement allemand en Fraktur** — indices de langue sur 6 pages :
  ~389 allemand contre ~36 français. Et les confusions Fraktur sont **dans
  l'ALTO lui-même** : `Cr erblickte bas Licht ber Welt` pour *Er erblickte
  das Licht der Welt* (d→b, E→C).

**Pourquoi il compte** : c'est exactement la matière sur laquelle H1 a
échoué. Le tester sert H2, pas H1.

**Sa limite, dite plutôt que tue** : même producteur que `37-GT-BNL`
(Bibliothèque nationale du Luxembourg). Il ne casse donc pas la corrélation
de producteurs déjà signalée dans `H1.md` — il ajoute de la matière, pas de
l'indépendance.

**Réserve mesurée** : certaines boîtes du source sont fausses, par exemple
`WIDTH="3"` pour `CONTENT="Humoristisch-satyrisches"`. Les fenêtres qui se
chevauchent sont déjà refusées par `corrupt.merge_cases`, mais une boîte
absurde mais non chevauchante passerait. À regarder avant de mesurer.

## ❌ Écarté — Reichsanzeiger-GT (UB Mannheim)

- <https://github.com/UB-Mannheim/reichsanzeiger-gt>, Zenodo
  `10.5281/zenodo.10144094`.
- 101 pages de journal allemand en Fraktur, PAGE XML. L'article annonce
  « 490 679 words ».
- **Vérifié : `<Word>` = 0.** Le PAGE publié ne porte que `TextRegion` et
  `TextLine`. Le décompte de mots de l'article est un comptage de tokens,
  pas une annotation géométrique.
- Inutilisable tel quel. C'est l'exemple qui justifie de vérifier plutôt que
  de lire les descriptions.

## ❌ Injoignable — Chronicling America (LoC)

`chroniclingamerica.loc.gov` ne répond plus (migration vers `loc.gov/apis`).
L'ALTO v2 + JP2 existent toujours via les *Bulk OCR Downloads*, mais la voie
d'accès est à retrouver. **Non vérifié.**

## ⏳ Pistes non vérifiées

Elles n'ont pas été téléchargées ; ne rien en conclure.

- **ÖNB / ANNO** (Autriche) — 2,1 millions de pages 1568-1877 en domaine
  public, IIIF à `iiif.onb.ac.at`. Fraktur. Reste à vérifier que l'ALTO
  porte des `String` géométriques.
- **Europeana Newspapers** — ALTO de plusieurs bibliothèques nationales,
  donc **plusieurs producteurs** : c'est la piste qui casserait vraiment la
  corrélation signalée dans `H1.md`.
- **Delpher / KB** (Pays-Bas), **Hemeroteca Digital / BNE** (Espagne) —
  autres producteurs, autres langues.

## Ce qui manque encore

Un corpus d'un **producteur entièrement distinct** de BnF/Gallica et de la
BnL. Europeana Newspapers est la meilleure piste pour ça.
