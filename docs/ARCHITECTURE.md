# Le système proposé — chaque pièce mesurée

Demande du mainteneur : *« trouve-moi un système pour gagner en correction
tout en ayant à la fin la bonne structure et les bonnes boîtes. »*

Les trois exigences se tiennent, et chacune a sa mesure.

```
        image de page + texte OCR de la page
                      │
                      ▼   UN appel
        ┌──────────────────────────────┐
        │  correcteur VLM, page entière│   3,7 %  (contre 8,3 % sans rien)
        └──────────────┬───────────────┘
                       │  texte corrigé, nombre de lignes NON garanti
                       ▼
        ┌──────────────────────────────┐
        │  reprojection au CARACTÈRE   │   gain intégralement conservé
        └──────────────┬───────────────┘
                       │  une ligne de sortie par ligne source
                       ▼
        ┌──────────────────────────────┐
        │  gardes saknussemm, par ligne│   refuse ce qu'elles ne cautionnent pas
        └──────────────┬───────────────┘
                       │  4 % des lignes ont changé de segmentation
                       ▼
        ┌──────────────────────────────┐
        │  résolveur CTC (la couture)  │   99,7 – 99,9 % de frontières justes
        └──────────────┬───────────────┘
                       ▼
                 ALTO corrigé
```

## 1. La correction — la page entière, en un appel

| | moyenne | appels/page |
|---|---|---|
| ne rien faire | 8,3 % | — |
| texte seul | 6,6 % | 1 |
| vision **par ligne** | 6,4 % | 4+ |
| **vision, page entière** | **3,7 %** | **1** |

**55 % d'erreur en moins.** Et ce n'est pas la résolution qui compte : à
1024 px le modèle fait mieux qu'à 2048. Ce qui manquait au recadrage par
ligne est le **contexte** — voir la ligne dans son paragraphe.

Valable aussi pour `small` : 7,3 % par ligne → **5,6 %** en page entière.

## 2. La structure — reprojection au caractère

Le prix du contexte : **2 à 4 pages sur 9** rendent un nombre de lignes faux.

`align_page_lines` de saknussemm sait recoller, mais il compare par
**jetons** — et une correction qui scinde un mot ne partage aucun jeton avec
sa source. Les lignes qui profitent le plus de la correction sont donc celles
que l'alignement refuse : **43 sur 251 perdues**, gain retombé de 3,7 % à
6,4 %.

| | brut | recollage par **jetons** | recollage au **caractère** |
|---|---|---|---|
| medium 1024 | 3,7 % | 6,4 % | **3,7 %** |
| small 1024 | 5,6 % | 5,9 % | **5,6 %** |

`hans.reproject` fait le second. **Contrôle à vide : 251/251** — reprojeter
un texte non corrigé rend la source à l'identique.

Le Jaccard n'était pas un mauvais choix : il a été validé contre une copie
**corrompue**, où les jetons survivent. Il devient faux contre une copie
**corrigée**, où ils ne survivent pas.

## 3. Les gardes — inchangées

Elles s'appliquent ligne à ligne comme aujourd'hui. Elles ne détectent pas
les hallucinations *sémantiques* — mesuré : `Classifieation` devenu
`Classifiation` est passé — mais les **violations de contrat**, et elles
coûtent environ 0,3 point de gain en refusant aussi de bonnes corrections.
C'est le prix explicite de la sûreté.

## 4. Les boîtes — le résolveur CTC sur 4 % des lignes

Seules les lignes dont la correction a changé le nombre de mots ont besoin
d'une géométrie neuve : **4,2 %** sur une page réelle.

| corpus | proportionnel | CTC routé |
|---|---|---|
| presse XIXᵉ (BnF, *Le Temps*) | 81–84 % | **99,8–99,9 %** |
| Fraktur (modèle assorti) | 79 % | **99,8 %** |
| français XVIIᵉ | 63,6 % | **99,7 %** |

Corroboré par **Tesseract**, moteur de lignée indépendante : 99,7 % sur *Le
Temps*, avec le meilleur pire cas. La contamination possible de CATMuS
n'explique donc pas le résultat.

## Ce qui reste à câbler

1. **Un producteur page-entière-avec-image.** `PageLLMEditProducer` déclare
   `wants_image = False` ; `VisionEditProducer` recadre par ligne. Aucun des
   deux n'envoie la page entière avec son image.
2. **Brancher `hans.reproject`** entre le producteur et les gardes.
3. **Le modèle CTC en paramètre de campagne** — la couture est mergée, la
   conformité prouvée.

## Ce qui n'est pas mesuré

- La chaîne **complète** bout en bout : chaque étage l'est séparément.
- Un corpus hors du jeu d'entraînement de CATMuS, pour la question
  ré-OCRisation contre post-correction.
- Le seuil vision `min_source_similarity = 0,15`, que le code lui-même
  qualifie de *« défaut sûr, pas calibré »*.
