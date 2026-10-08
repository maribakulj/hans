# hans

> Hans ne parle pas. Il montre où est le chemin.

**Where the words are.** `hans` ne lit pas le texte : il dit à quels pixels
il correspond. C'est le résolveur de géométrie que
[saknussemm](https://github.com/maribakulj/saknussemm) appelle quand une
correction déplace une frontière de mot et que les boîtes ALTO d'origine ne
décrivent plus ce qui est écrit.

## Le problème

saknussemm corrige du texte OCR sans toucher à la structure. Quand la
correction est 1→1 — `president` → `président` — il garde la boîte
existante, et c'est la bonne réponse. Mais quand elle change la
segmentation :

```
ALTO :   <String CONTENT="dela" HPOS="100" WIDTH="41"/>
corrigé : de la
```

il faut deux boîtes là où il n'y en avait qu'une, et personne ne sait où
couper. Aujourd'hui saknussemm répartit la largeur au prorata du nombre de
caractères. C'est honnête, c'est déterministe, et ça ne regarde pas l'image.

`hans` regarde l'image.

## Le but

> saknussemm sait réparer la géométrie ALTO quand la correction change la
> segmentation, et sait dire avec quelle confiance — **ou bien** on a la
> preuve mesurée que le CTC ne le permet pas sur du patrimonial français,
> et on l'écrit.

Le « ou bien » n'est pas une clause de style. Voir `AUTOPILOT.md`.

## Le juge d'abord

L'hypothèse qui décide de tout — **H1 : l'alignement CTC bat-il la
répartition proportionnelle ?** — ne vaut que si la mesure est incorruptible.
Ici elle l'est, parce que la vérité terrain est *fabriquée mécaniquement* et
jamais choisie :

1. prendre deux mots voisins dont l'ALTO donne déjà les boîtes ;
2. les coller en une seule String dont la boîte est **l'union** — ce n'est
   pas une invention, c'est exactement ce qu'aurait écrit un producteur qui
   a mal segmenté ;
3. demander au résolveur où recouper ;
4. la réponse était connue au pixel près, et personne ne l'a choisie.

Aucune campagne d'annotation, aucun corpus à étiqueter, et un banc qui
tourne sans modèle, sans réseau et sans clé.

La direction inverse (fabriquer des scissions) est **volontairement absente** :
pour l'inventer il faudrait décider où couper, et toute règle pour le décider
est l'hypothèse que la ligne de base incarne déjà. Le corpus serait bâti sur
la supposition de l'accusé. Voir `src/hans/corrupt.py`.

## Utilisation

```bash
python -m hans.bench chemin/vers/page.xml
```

## État

| | Jalon | État |
|---|---|---|
| G0 | La couture `WordGeometryResolver` dans saknussemm | fait ; le fil restant (le résolveur interrogé quand la page devine) est la PR saknussemm #172, `last_resort` |
| G1 | **Le juge** — banc, corruption mécanique, ligne de base | fait |
| H1 | CTC vs proportionnel, 3 corpus | **tranchée : RÉFUTÉE** — voir [docs/H1.md](docs/H1.md) |
| G2 | `CTCCutsResolver` | écrit et mesuré |
| G3 | `alignment_confidence` | clos sans être fait (contrat : H1 réfutée) |
| G4 | Bout en bout | clos sans être fait (contrat : H1 réfutée) |
| — | Contre-revue externe du 7/10/2026 : dix défauts du banc | **corrigés** le 8/10 — verdict non déclarable sur populations incomparables, reprojection avec signaux, provenance des caches CTC, `--strict` rejoue la parité, voir `AUTOPILOT.md` |
| H27 | Post-correction sans décodeur (`~/axel`) : porte des phases 0 à 3 | **mesurée** — un étiqueteur d'éditions de 1,4 M de paramètres n'invente rien (0 suite ≥ 3 sur 6 066 lignes), dégrade 0,98 % des lignes propres (LLM nu 12,7 %, LLM sous gardes 5,3 %), réduit le CER modéré de 14 % ; H2, H5, H6 tenues, H1 et H3 attendent Colab, voir [docs/H27.md](docs/H27.md) |
| H26 | La « vérité terrain » NewsEye relue à l'œil | **mesurée** — 200 lignes : les 5 pages Transkribus de 1937 sont une transcription humaine (0,2 % d'erreurs), les 3 pages BnF sont un OCR (5,5 %, 41 lignes fautives sur 75) ; leur texte sort de toute référence, voir [docs/H26.md](docs/H26.md) |
| H25 | PAGE : garder les `Word`, découper le reste dans les polygones existants | **mesurée** — 98,8 % et 96,2 % de bout en bout là où le chemin lent supprimait tous les mots ; PR saknussemm en attente de validation (règle de spec), voir [docs/H25.md](docs/H25.md) |
| H24 | Le test réel : Tesseract corrigé par la vérité terrain, boîtes d'un autre producteur | **mesurée** — chemin lent 50,8 → 89,5 % sans image, 91,7 % avec le CTC en dernier recours (un tiers des appels) ; 97,6–98,2 % sous 15 % d'erreurs OCR, voir [docs/H24.md](docs/H24.md) |
| H23 | La demi-ligne inventée (VR-12) | **mesurée** — aucun signal textuel ne sépare l'invention de la fin de ligne retrouvée sur l'image ; un garde en option arrête les 25 fautives pour 18 justes sur 6 077 corrections, voir [docs/H23.md](docs/H23.md) |
| H22 | Réparation locale sans pixels : garder les boîtes, n'ouvrir que la boîte touchée | **mesurée sur 25 corpus** — 97 à 99,8 % sur les ALTO de bibliothèque, implémentée dans saknussemm (PR #167), voir [docs/H22.md](docs/H22.md) |
| H21 | Largeurs de glyphes apprises : dans les trous du CTC, et sans pixels depuis l'ALTO | **mesurée** — voir [docs/H21.md](docs/H21.md) : la variante CTC ne déplace rien ; la variante sans pixels divise la queue par 2 à 6 mais aggrave le pire cas sur deux corpus. **Supersédée par H22** (2026-10-01) : les largeurs apprises servent à placer les mots entre des boîtes gardées, pas à pondérer le prorata d'une ligne entière — le pire cas de H21 ne se pose plus |

**En une phrase** : le CTC fait passer la part des frontières mal placées de
~16-21 % à moins de 1 % sur les trois corpus — mais il aggrave le pire cas
sur l'un d'eux, ce que le critère interdit. La cause est identifiée et
étroite : un recognizer d'imprimé français est hors domaine sur les lignes
en Fraktur d'un corpus luxembourgeois, et il produit là une géométrie
confiante et fausse.

## Licence

Apache-2.0.
