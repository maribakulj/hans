# Autopilot — la file de travail autonome de `hans`

Ce fichier est **l'état**, pas un compte rendu. Une session réveillée n'a pas
mon contexte : elle a ce fichier, le dépôt, et rien d'autre. Si les deux se
contredisent, **le code gagne** et ce fichier est corrigé.

Dernière mise à jour : 2026-09-21.

---

## Le but

> `saknussemm` sait réparer la géométrie ALTO quand la correction change la
> segmentation, et sait dire avec quelle confiance — **ou bien** on a la
> preuve mesurée que le CTC ne le permet pas sur du patrimonial français,
> et on l'écrit.

Le « ou bien » est une issue réelle. Une boucle dont le but ne peut que
réussir ne s'arrête jamais.

---

## Décisions du mainteneur — 2026-09-21

Prises explicitement, contre mon avis sur les deux dernières. Elles sont
déléguées : la boucle les applique sans les rouvrir.

1. **Le dépôt distant est `maribakulj/hans`, privé.** La boucle y pousse.
2. **La boucle va jusqu'au verdict de H1 inclus.** J'avais recommandé de
   s'arrêter avant : un verdict n'a pas de juge externe. Contre-mesure posée
   en conséquence — `src/hans/verdict.py` calcule le verdict à partir du
   critère gelé, et `test_verdict.py` épingle ce critère sur le texte de ce
   fichier. Déclarer H1 est devenu une opération arithmétique, pas une
   interprétation. **Le critère ne se renégocie pas au moment de mesurer.**
3. **La boucle choisit seule le troisième corpus.** J'avais recommandé de
   préparer des candidats. En contrepartie, la règle 3 s'applique avec
   sévérité : représentativité vérifiée AVANT de mesurer, fiche écrite au
   journal, et la règle 9 (le corpus porte-t-il l'ENTRÉE ou la réponse ?)
   vérifiée explicitement et écrite.

---

## Le contrat de boucle

**L'unité de travail est le geste ; « vert » est la condition de sortie de
chaque tour.** La boucle **pousse ses commits** — décision du mainteneur, le
2026-09-21. Elle ne demande pas de relecture avant de pousser ; en échange,
elle ne pousse que du vert, et « vert » veut dire les quatre à la fois :

```
ruff check src tests && ruff format --check src tests
&& mypy src/hans && pytest -q
```

Ordre de priorité à chaque réveil, sans exception :

1. **Suite rouge → c'est ça le travail.** Rien d'autre ne commence.
2. **Vert et file non vide** → l'item non clos le plus haut, un geste, un
   commit, un push.
3. **Sinon** → arrêt, avec la raison au journal.

**Le vert local ne vaut pas le vert de la CI** : elle tourne sur 3.11, 3.12
et 3.13, et **sans** `saknussemm` (le paquet n'est pas publié — la Phase 3 de
saknussemm est bloquée sur le mainteneur). C'est délibéré : le banc doit
tourner là où il n'y a ni modèle, ni réseau, ni clé, sinon la boucle n'a pas
de moteur.

---

## Règles permanentes

Les règles 1 à 5 sont **reprises telles quelles de l'AUTOPILOT de
saknussemm**. Elles ont été payées là-bas, elles s'appliquent mot pour mot
ici, et ce dépôt est *plus* exposé qu'elles : saknussemm a une CI comme juge
externe, un projet de mesure n'en a pas.

1. **Un geste, un commit vert.** Les quatre vérifications avant chaque
   commit.
2. **En cas de doute, s'arrêter et écrire la question** dans `## Questions`.
   Ne jamais trancher un arbitrage de conception seul.
3. **Choisir un corpus pour sa TAILLE est un biais, pas une commodité.**
   Vérifier la représentativité AVANT de mesurer.
4. **Un résultat qui va dans le sens espéré demande plus de vérification
   qu'un résultat décevant, pas moins.** Lire les DONNÉES, jamais seulement
   les compteurs. *Déjà encaissé ici : voir le journal du 2026-09-21.*
5. **Sur une chaîne vision, REGARDER le crop avant de juger le modèle.**
   L'ALTO de `37-GT-BNL` est en **dixièmes de millimètre** (facteur
   `300/254`) ; sans transformation, chaque crop est décalé de 18 %, de plus
   en plus bas en descendant la page — donc plausible, jamais vide. Ça a
   déjà coûté deux campagnes complètes à saknussemm, **deux fois**. Écrire le
   crop sur disque et le regarder coûte trente secondes.

9. **Lire le README AVANT le premier grep.** Payé le 2026-09-21 : une
   soirée entière à mesurer, écrire et corriger un mode « bloc » qui existait
   déjà dans saknussemm sous le nom `PageLLMEditProducer`, documenté en
   section 4 du README sous le titre « Two modes, and the one thing that
   separates them », avec le tableau des coûts. Un grep trouve ce qu'on sait
   nommer ; il ne trouve jamais ce qu'on n'a pas pensé à nommer. Avant
   d'ouvrir une hypothèse sur un dépôt : son README, puis la liste de ses
   paquets publics, puis le premier paragraphe du docstring de chaque module.
   Ensuite seulement, chercher.

10. **Demander « que fait déjà ce code ? » avant « ce code permet-il mon
    idée ? ».** Même date, même facture. Un document de conception reçu n'est
    pas un cahier des charges : c'est une proposition, et la première chose à
    faire est de la confronter à ce qui est déjà construit.

Et trois que la nature de ce dépôt impose :

6. **Une mesure prise là où le test de parité a SAUTÉ n'est pas une mesure.**
   La ligne de base est une *copie* du `_compute_geometry` de saknussemm ; si
   `test_baseline_is_saknussemms.py` n'a pas tourné, elle est non épinglée et
   la comparaison se fait contre un épouvantail. `bench --strict` refuse de
   tourner dans un tel environnement — **toute mesure au journal doit avoir
   été prise avec `--strict`.**
7. **Le critère de réussite se fixe AVANT la mesure** (voir H1). Un seuil
   choisi après coup n'est pas un seuil.
8. **Ne jamais fabriquer de cas de scission.** Il faudrait décider où couper,
   et toute règle pour le décider est l'hypothèse que la ligne de base
   incarne. Le corpus serait bâti sur la supposition de l'accusé. Voir
   `src/hans/corrupt.py`, qui explique pourquoi une seule direction est
   utilisable.

---

## Les objectifs émergents

La boucle absorbe du travail neuf, mais **typé** — sans quoi elle
s'auto-alimente indéfiniment, ce qui est le mode d'échec propre à un sujet de
recherche.

| Type | Ce que c'est | Autorisé seule ? |
|---|---|---|
| **A** | Régression : suite rouge, test qui casse | **Oui** — priorité absolue |
| **B** | Sous-tâche d'un jalon **déjà ouvert** | **Oui** — entre dans la file |
| **C** | Nouveau jalon, changement de cap, dépendance, hypothèse neuve | **Non** — s'écrit dans `## Questions`, la boucle passe à autre chose |

Un C déguisé en B est la faute à ne pas commettre : « pendant que j'y suis,
j'entraîne un petit recognizer » est un C.

---

## Conditions d'arrêt

La boucle s'arrête — et écrit pourquoi au journal — dès que l'une est vraie :

- la suite est rouge pour une cause qu'on ne sait pas lire après une
  tentative ;
- l'item suivant exige clés, réseau, budget, licence ou décision humaine ;
- l'item suivant est un **C** ;
- deux réveils consécutifs sans progrès mesurable ;
- **un résultat va dans le sens espéré et n'a pas été contre-vérifié sur les
  données** (règle 4 promue en condition d'arrêt) ;
- **une mesure a été prise sans `--strict`** ;
- **H1 est tranchée** — dans un sens ou dans l'autre ;
- la file est vide.

---

## La file

### 0. Tests des branches neuves de `G0` — **en tête**

`_geometry_is_usable` et `_resolve_geometry` (saknussemm,
`formats/alto/rewriter.py`) n'ont **aucun test**. La suite est verte parce
que le chemin par défaut est inchangé ; les branches neuves ne sont
exercées par rien. À couvrir : compte de tokens faux, texte qui ne
correspond pas, largeur nulle, chevauchement, débordement de la boîte,
résolveur qui lève — et le cas nominal, où un résolveur valide passe.

**Fini quand** : chaque branche de `_geometry_is_usable` a un test qui
échoue si on la retire.

### 1. `G0` — la couture dans saknussemm

Exposer `WordGeometryResolver` dans `saknussemm/core/protocols.py`, avec le
comportement actuel comme implémentation par défaut, et la brancher sur
`formats/alto/rewriter.py:1037`.

**Contraintes non négociables** : zéro dépendance ajoutée, l'invariant `I4`
(cécité aux pixels, `tests/test_import_contract.py:287`) intact, sortie
identique à l'octet près quand aucun résolveur n'est fourni. Les tests
`test_public_api_snapshot.py`, `test_public_surface_is_the_closure.py` et
`test_internal_seams_are_named.py` vont réagir : c'est attendu, pas une
panne.

**Fait le 2026-09-21** pour la couture elle-même (commit `11471e2`) :
Protocol, `_geometry_is_usable`, `_resolve_geometry`, 1792 tests verts,
`I4` intact, zéro dépendance.

**Reste — et c'est un arbitrage du mainteneur, pas de la boucle** :
`rewrite_alto_file` ne reçoit pas encore le résolveur. Deux paramètres de
plus la font passer de 161 à 166 lignes, et `test_orchestrator_budget` la
tient à « ne peut que rétrécir ». Le garde-fou a raison — la fonction est
déjà trop grosse — et la règle 5 de saknussemm interdit de découper ce
fichier. Relever l'épingle est une décision de conception. **La boucle ne la
prend pas.** H1 n'en dépend pas : le banc n'appelle pas `rewrite_alto_file`.

### 2. `H1` — le CTC bat-il le proportionnel ? **← le jalon qui décide**

Mesure : `CTCForcedAlignmentResolver` contre `ProportionalResolver`, au banc,
sur **au moins trois corpus** dont un qui n'est ni `BnF-bpt6k3265015q` ni
`37-GT-BNL` (règle 3 : deux corpus ne sont pas un échantillon).

**Critère de réussite, fixé le 2026-09-21, avant toute ligne de CTC** — et
il ne bouge plus (règle 7) :

> Le CTC **réduit de moitié** la part des frontières au-delà de 0,5 caractère
> sur **au moins deux corpus sur trois**, **et** n'aggrave le pire cas sur
> aucun.

Repères mesurés ce jour, ligne entière, `--strict` :

| corpus | frontières | ≤ 0,5 car. | moyenne | pire |
|---|---|---|---|---|
| `BnF-bpt6k3265015q` | 2 773 | **92,6 %** | 0,11 car. | 3,79 car. |
| `37-GT-BNL` | 3 083 | **87,3 %** | 0,17 car. | — |

Donc la cible est : **≥ 96,3 %** sur BnF, **≥ 93,7 %** sur 37-GT-BNL.

**Fini quand** : le verdict est écrit ici, quel qu'il soit. Si H1 est
réfutée, `G2`/`G3`/`G4` sont clos sans être faits, et le dépôt devient le
compte rendu d'une réfutation — ce qui est un résultat.

### ~~3. `G2`~~ — **fait** sous la forme `CTCCutsResolver`

`kraken.align.forced_align` existe déjà et rend, par caractère, un couple
`(début, fin)` **déjà remis à l'échelle de l'image** plus une confiance
(`kraken/align.py:81-83`). Il n'y a pas de modèle à entraîner pour répondre à
H1 : il y a un appel à câbler.

⚠️ L'hypothèse à tester en premier dans G2 : les émissions d'un recognizer
restent-elles informatives sur du français ancien (ſ long, ligatures) ? Si
elles ne le sont pas, l'alignement dérive **silencieusement**.

### ~~4. `G3`~~ — **clos sans être fait** (contrat : H1 réfutée)

Le rapport vraisemblance du chemin forcé / décodage libre. **Pas** un verdict
« unmatched » : un alignement forcé trouve toujours *un* chemin, quitte à
écraser un mot dans deux frames. Le signal est un score bas, pas un échec
d'appariement.

### ~~5. `G4`~~ — **clos sans être fait** (contrat : H1 réfutée)

---

## Passe la main au mainteneur

Hors de portée de la boucle, et ce n'est pas un problème à contourner :

- **créer le dépôt distant** `hans` et pousser (compte GitHub) ;
- **un troisième corpus** pour H1, avec image et ALTO au mot ;
- publier `saknussemm` sur PyPI (débloquerait `[parity]` en CI).

---

## Questions ouvertes

- **Séparer plausibilité et attachement — RETIRÉ le 2026-09-23.** Le
  recours par les pixels admettait 3 lignes sur 20 sur un score. Le
  mainteneur exige zéro ligne mal rattachée, quitte à refuser. Remplacé par
  le veto par marge de H12, mesuré à zéro sur tout ce qui a été cherché, et
  qui reste sous `I4`. Ce qui demande arbitrage maintenant : ajouter ce veto
  comme garde de saknussemm (une *marge* contre les voisines, en plus du
  plancher `min_source_similarity`), et un producteur line-keyed compact
  avec image de page. **C**.
- **La géométrie verticale.** Tout ici est horizontal. Un polygone par mot
  demande un masque d'encre (§9 du récapitulatif) et c'est un jalon qui
  n'existe pas encore. **C** — ne pas l'ouvrir sans arbitrage.
- **Un seuil de support plus strict, ou un routage par écriture.** H1 échoue
  sur deux frontières d'une ligne en Fraktur que le seuil de 0,5 laisse
  passer. Relever ce seuil *maintenant*, après avoir vu quelles lignes
  échouent, serait exactement l'ajustement que ce dépôt existe pour
  empêcher : ce serait une hypothèse neuve (H2), à geler avant de mesurer, et
  de préférence sur un quatrième corpus jamais regardé. **C** — arbitrage du
  mainteneur.
- **La césure.** Une fusion `N→1` à cheval sur deux `TextLine` ne peut pas
  être l'union de deux boîtes : ALTO a `SUBS_TYPE="HypPart1/HypPart2"` pour
  ça, et saknussemm a déjà `core/hyphenation.py`. Le banc ne fabrique aucun
  cas de ce type aujourd'hui. Faut-il ? **C**.

---

## Journal

### 2026-09-21 — amorçage, et le banc contredit tout de suite l'intuition

`G1` fait : lecteur ALTO, corruption mécanique, métrique, ligne de base,
33 tests, CI sur trois versions. Parité avec le `_compute_geometry` de
saknussemm épinglée (20 cas, espaces insécables compris).

**Premier résultat, et il a failli être faux.** Le banc, tel qu'il était
d'abord écrit, collait *deux mots voisins* et rendait **99,8 %** de
frontières correctes pour la ligne de base — de quoi conclure qu'il n'y a
aucun problème à résoudre.

C'était un défaut du harnais, pas un résultat. La boîte formée par deux mots
voisins est tenue par deux vrais bords distants de quelques caractères : il
n'y a presque pas de place pour se tromper. Or `rewriter.py:1037` appelle
`_compute_geometry` avec la largeur de **toute la ligne** et **tous** ses
tokens : sur le chemin lent, saknussemm jette *toutes* les boîtes de mots et
redistribue la ligne entière. Le banc mesurait une réparation que personne
n'effectue.

Corrigé — le cas par défaut est la ligne entière. L'erreur croît
régulièrement avec la fenêtre (0,005 → 0,151 caractère de 2 à 12 mots), ce
qui est la signature attendue d'une accumulation avec la distance aux bords,
et confirme que la courbe mesure bien quelque chose.

**Ce que ça change pour le projet.** La marge du CTC n'est pas « la géométrie
est cassée ». C'est **7 à 13 % des frontières**, avec une queue jusqu'à
3,8 caractères. C'est réel et ça vaut d'être réparé — mais c'est une cible
étroite, et elle était inconnue il y a une heure. Le critère de H1 est fixé
là-dessus, avant qu'une seule ligne de CTC existe.

Ce que la règle 4 a attrapé ici, ce n'est pas un chiffre flatteur pour un
modèle : c'est un chiffre flatteur pour **l'incumbent**, qui aurait fait
annuler le projet. Elle marche dans les deux sens.

### 2026-09-21 (suite) — le corpus, le modèle, et un piège dans kraken

**Item 0 fait** (saknussemm `d912714`, branche `couture-geometrie-mot`) :
`_geometry_is_usable` et `_resolve_geometry` ont 13 tests, un par refus.
1805 tests verts.

**Troisième corpus choisi — et la règle 3 appliquée avant de mesurer.**
`tests/external_corpus/pinned` de saknussemm épingle trois documents Gallica
avec leur sha256 : monographie 1850 (*Histoire naturelle*), monographie 1850
mode texte (*Périodes de l'histoire de la médecine*), quotidien
multi-colonnes 1890 (*Le Temps*). Les trois portent des `String` avec
`HPOS`/`WIDTH` et `WC`.

- **Images** : l'API IIIF de Gallica répond (200), contrairement aux accès
  agent bloqués ailleurs. `https://gallica.bnf.fr/iiif/ark:/12148/<ark>/f<n>/full/full/0/native.jpg`.
- **Règle 10, vérifiée AVANT de mesurer** : l'image rendue fait 1749×2481 et
  l'ALTO déclare `WIDTH="1749" HEIGHT="2481"`. **Facteur 1, aucune
  transformation.** Ce n'est pas le piège `300/254` de `37-GT-BNL`.
- **Limite du corpus, écrite plutôt que tue** : deux des trois corpus
  (`BnF-bpt6k3265015q` et celui-ci) viennent de la même chaîne de production
  BnF/Gallica. La règle « deux sur trois » est donc moins indépendante
  qu'elle en a l'air. À dire dans le verdict, quel qu'il soit.
- **Encodage** : ces ALTO déclarent `ISO-8859-1` et contiennent de l'UTF-8.
  `CONTENT` doit passer par `.encode('latin-1').decode('utf-8')`, sinon
  « raisonnée » arrive comme « raisonnÃ©e » et le codec du modèle rejette la
  séquence.

**Modèle : CATMuS-Print Large** (`10.5281/zenodo.10592716`, 22,9 Mo),
diachronique pour les imprimés français.

**Le risque principal de G2 est levé.** J'avais écrit qu'il fallait vérifier
en premier si les émissions restent informatives sur du français ancien. Un
décodage **libre** sur six lignes de 1850 : le modèle lit juste, et il
*corrige* même l'OCR de l'ALTO — `zooloÃ¢idue` (ALTO) contre `zoologique`
(modèle), `l'ouÃ¯e` contre `l'ouie`. Les émissions ne dérivent pas.

Note de méthode : la « prediction » que rend `forced_align` est le texte
cible ré-émis caractère par caractère. Elle ne prouve **rien** sur le modèle.
Seul le décodage libre le prouve, et c'est celui-là qu'il faut regarder.

**Piège trouvé dans kraken — `kraken.align.forced_align` est inutilisable.**
Le module est déprécié (« will be removed with kraken 8 ») et il est cassé
avec ce modèle : il fait `torch.tensor(model.outputs).log_softmax(0)` sur des
sorties **déjà normalisées**. Chaque trame ajoute alors un coût quasi
constant, le chemin forcé a donc intérêt à finir au plus tôt, et
`argmax(trellis[:, -1])` tombe exactement sur le nombre de caractères : 18
trames pour 18 caractères là où la ligne en compte 116. Les boîtes sortent
comprimées contre le bord gauche — **plausibles, jamais vides**, donc du
genre qu'on ne remarque pas sans regarder les vrais bords à côté.

`kraken.tasks.ForcedAlignmentTaskModel` est la voie correcte : il travaille
sur `record.logits` bruts et recalcule `net.in_scale` par ligne.

**L'alignement forcé de kraken est cassé dans les DEUX voies.**
`kraken.tasks.ForcedAlignmentTaskModel` rend exactement la même compression
que la voie dépréciée : 18 découpes tassées sur 52 px pour une ligne de
361 px. Ce n'est donc pas l'enveloppe `BaselineOCRRecord`, c'est le trellis :
`argmax(trellis[:, -1])` tombe sur le nombre de caractères, donc le chemin se
termine au plus tôt. Diagnostic non clos — mais inutile de le clore, parce
qu'il existe mieux.

**Ce qui marche : le décodage NORMAL et ses propres découpes.**
`rpred` rend un `cuts` par caractère de sa propre prédiction, et ceux-là sont
justes :

| mot | découpes CTC | vrai (ALTO) |
|---|---|---|
| `Classer` | 443..559 | 437..571 |
| `déterminer` | 930..1129 | 928..1141 |
| `avoir` | 819..899 | 816..913 |
| `de` | 543..569 | 538..584 |

Les découpes sont systématiquement un peu plus SERRÉES que les boîtes ALTO —
attendu : le CTC épouse l'encre, l'ALTO garde une marge. Ce qui compte n'est
pas la boîte mais la frontière, et les frontières tombent dans les blancs.

**Conséquence sur la conception de `G2`** — et c'est une mesure qui la
dicte, pas une préférence :

1. décoder la ligne normalement → texte lu + une découpe par caractère ;
2. aligner le texte lu sur le texte CIBLE (la correction) — saknussemm sait
   déjà le faire, `core/alignment.py` ;
3. reporter les découpes sur les frontières de mots de la cible.

C'est plus robuste que l'alignement forcé : quand le modèle se trompe, on
aligne deux textes au lieu de forcer un chemin dans des émissions qui ne
portent pas ce qu'on leur impose.

**Piège d'exécution à retenir** : `model.predict` de kraken passe par du
multiprocessing. Sans garde `if __name__ == "__main__":` chaque worker
réexécute le script entier et la machine part en boucle de spawn. Le
résolveur doit être import-safe.

**`CTCCutsResolver` écrit et mesuré sur un corpus.** Cache de découpes
produit hors de `hans` (`tools/decode_lines.py`, lancé par le venv kraken) et
lu par un résolveur en Python pur : la CI reste installable sans les 2 Go de
torch, et la campagne devient auditable — le texte lu est sur le disque à
côté des chiffres qu'il a produits.

**Et le banc m'a menti une deuxième fois, dans l'autre sens.**
Premier score du CTC : **100,0 % des frontières correctes, erreur nulle,
partout**. Un score parfait n'est presque jamais un résultat.

Cause, trouvée en regardant les largeurs : les découpes CTC épousent l'encre
tandis que les boîtes ALTO gardent une marge, donc le blanc *prédit* fait le
double du vrai (36 px contre 17 en médiane) et le **contient** à chaque fois.
Comparer intervalle contre intervalle rendait « ils se chevauchent »
gratuit : **la métrique récompensait l'imprécision**, et un résolveur rendant
un blanc large comme la ligne aurait obtenu 100 %.

Corrigé : la prédiction est notée sur le **point médian** du blanc, pas sur
son étendue. Un blanc large centré sur la coupe vaut toujours zéro — le
résolveur a bien localisé la frontière — mais il est pénalisé dès qu'il est
décentré, ce que la version par intervalles ne pouvait pas voir.
`test_a_gigantic_space_does_not_score_zero` épingle le défaut.

**Le critère de H1 n'a pas bougé** : il est énoncé comme une *règle* sur la
ligne de base (« réduire de moitié »), pas comme des nombres, donc remesurer
les deux côtés redérive les cibles. C'est précisément pour ça qu'il a été
gelé sous forme de règle.

**Mesure, métrique corrigée, `bpt6k2206225` p.15 — 194 frontières :**

| résolveur | ≤ 0,5 car. | moyenne | pire |
|---|---|---|---|
| proportionnel | 83,0 % | 0,20 car. | 34 px |
| **CTC** | **100,0 %** | 0,00 car. | 1,5 px |

**Règle 10 appliquée : le crop a été dessiné et regardé**
(`/tmp/check_boundaries.png`). Le crop tombe sur le bon texte — donc pas de
décalage d'échelle —, les blancs vrais sont là où le banc les place, les
marques CTC tombent dedans et les marques proportionnelles dérivent de plus
en plus en avançant dans la ligne. Ce que les chiffres disaient, l'image le
montre.

**Ce n'est pas H1.** Une page, un corpus. Le critère en exige trois.

**Prochain obstacle, connu d'avance** : `37-GT-BNL` est en dixièmes de
millimètre (facteur `300/254`). Décoder ses lignes sans transformation
donnerait des crops décalés de 18 %, plausibles et jamais vides. À traiter
explicitement avant toute mesure sur ce corpus.

### 2026-09-21 (suite 2) — le candidat existe, et il gagne sur deux corpus

`CTCCutsResolver` complet : appariement plié (sans casse ni accents),
**repli sur le proportionnel** quand moins de la moitié de la cible est
ancrée dans ce que le modèle a lu. Ce repli n'est pas une commodité : c'est
ce que la couture de saknussemm fait déjà, donc c'est le seul candidat dont
la mesure décrive ce qui serait réellement livré. Noter un refus comme un
échec laisserait le candidat améliorer son pire cas en déclinant les lignes
difficiles.

**Deux bugs à moi, tous deux silencieux.**

1. Plier la chaîne entière change sa longueur ; l'aligneur travaille sur le
   texte plié, les positions sont indexées dans l'original. Le candidat est
   tombé de 99,6 % à 77,7 % **sans que rien ne lève**. Pliage désormais
   caractère à caractère, invariant épinglé.
2. Le garde-fou d'échelle comparait l'étendue des *lignes* à la largeur de
   l'image, et aurait refusé un corpus parfaitement calé (1,247) parce
   qu'aucune ligne n'atteint le bord de page. Il lit maintenant le `WIDTH`
   déclaré par `Page`. Un garde qui crie au loup finit désactivé.

**Mesures, métrique du point médian, `--strict` :**

| corpus | résolveur | ≤ 0,5 car. | pire |
|---|---|---|---|
| `bpt6k2206225` p.15 | proportionnel | 83,0 % | 34 px |
| | **CTC** | **100,0 %** | 1,5 px |
| `BnF-bpt6k3265015q` | proportionnel | 84,4 % | 207,5 px |
| | **CTC** | **99,8 %** | 59,5 px |

**Échelle vérifiée partout avant de mesurer** : les trois pages Gallica
déclarent exactement la largeur de leur image (facteur 1) ; `37-GT-BNL` est
bien à `1,1811` et est décodé avec, le garde-fou refusant toute autre valeur.

**Piège évité** : `37-GT-BNL` porte 509 lignes pour **40 identifiants
distincts**. Un cache fusionné aurait donné à la moitié des lignes la
géométrie d'une autre page, en silence. D'où `score_many`, qui garde un
résolveur par fichier et ne met en commun que les erreurs.

**En cours** : décodage de `Le Temps` (1103 lignes) et des 40 fichiers
`37-GT-BNL`. Ensuite `python -m hans.campaign campaigns/h1.json --strict`,
qui appellera `verdict.decide`. **Le verdict n'est pas encore rendu** : il
faut trois corpus et il n'y en a que deux de mesurés.

### 2026-09-21 (suite 3) — H1 sort « confirmée », et la vérification trouve un bug

Campagne complète, trois corpus, `--strict`, verdict calculé par
`verdict.decide` :

```
BnF-bpt6k3265015q   au-dela 0.5car: 15,58% ->  0,22%  (cible  7,79%)  OK
Gallica-pinned      au-dela 0.5car: 18,95% ->  0,06%  (cible  9,47%)  OK
37-GT-BNL           au-dela 0.5car: 20,99% ->  5,38%  (cible 10,49%)  OK
H1 CONFIRMEE -- 3/3 corpus, pire cas jamais aggravé.
```

**Et la règle 8 a payé une troisième fois.** Un chiffre détonnait :
**145 lignes déclinées sur 509** pour `37-GT-BNL`, contre 4 sur 538 et 1 sur
1174 ailleurs.

Cause, trouvée en dessinant les crops (règle 10) : ils sont **parfaitement
calés et parfaitement lisibles**, mais le modèle rend une chaîne **vide**.
Le point commun de ces lignes est leur bord droit, à `x = 689` ou `690` pour
une image large de 689. Corrélation mesurée sur tout le corpus :

| | lue | vide |
|---|---|---|
| ligne entièrement dans l'image | **364** | 0 |
| ligne touchant un bord | 0 | **145** |

Partition parfaite. L'extracteur de polygone de kraken ne sait pas prendre un
crop qui sort de l'image, et il ne le signale pas : il rend du vide.

**Ce que ça faisait à la mesure.** Une lecture vide ne coûte aucune erreur —
elle fait décliner le résolveur, qui rend la ligne au proportionnel. Donc sur
**28 % de ce corpus**, la campagne mesurait la ligne de base tout en
l'annonçant comme le candidat. Le score de `37-GT-BNL` était un mélange des
deux, pas une mesure du CTC.

Corrigé : les coordonnées mises à l'échelle sont bornées à l'image.
Redécodage en cours, campagne à relancer. **Le verdict ci-dessus ne vaut
rien tant qu'elle n'a pas retourné.**

Noter la direction : le bug ne flattait pas le candidat, il le *diluait*.
Le corriger va probablement renforcer le résultat — ce qui oblige à le
regarder avec plus de méfiance encore, pas moins.

### 2026-09-21 (suite 4) — H1 tranchée : RÉFUTÉE. La boucle s'arrête.

Caches corrigés, campagne relancée. Le bornage des crops a fait tomber
`37-GT-BNL` de 5,38 % à **0,62 %** de frontières au-delà du demi-caractère —
mais il a découvert le pire cas que le repli masquait : **146 px contre 84**
pour la ligne de base.

```
H1 REFUTEE -- le pire cas est aggrave sur 37-GT-BNL : le critere
l'interdit sur tout corpus, quel que soit le gain moyen.
```

**Avant la correction du bug, H1 sortait CONFIRMÉE.** C'est en réparant une
dilution qui *desservait* le candidat qu'on a découvert qu'il échouait. Le
verdict-en-code a fait exactement ce pour quoi il a été écrit : il n'a pas
laissé « la précision a été multipliée par dix » emporter la décision.

Cause identifiée et étroite : deux frontières, une seule ligne, en **allemand
composé en Fraktur**. `CATMuS-Print` est un modèle d'imprimé français, hors
domaine sur du Fraktur ; `37-GT-BNL` est luxembourgeois donc bilingue. 22
lignes passent avec un support entre 0,5 et 0,7 — toutes allemandes — et le
seuil de 0,5 ne les arrête pas.

Rapport complet : `docs/H1.md`.

**La boucle s'arrête** — condition d'arrêt « H1 est tranchée », prévue au
contrat. `G3` et `G4` sont clos sans être faits, comme le contrat le prévoit
aussi en cas de réfutation.

### 2026-09-21 (suite 5) — le code qui portait le verdict n'avait pas de tests

`hans/resolvers/ctc.py` et `hans/campaign.py` : **zéro test**. `hans/cuts.py` :
effleuré par un seul. Or `transfer` et `support` sont exactement ce sur quoi
repose la conclusion publiée dans `docs/H1.md`. Même défaut que l'item 0 de
saknussemm, et plus grave ici puisqu'une conclusion en dépend. 45 → **78
tests**.

Ce qui est désormais épinglé :

- le contrat de `transfer` — une boîte par token, monotone, dans la boîte de
  ligne, largeur ≥ 1 — y compris sur une lecture qui ne partage **rien** avec
  la cible, cas où une géométrie inadmissible serait rejetée en bloc par la
  couture ;
- **huit cas prouvant que toute réponse passe `_geometry_is_usable`** de
  saknussemm (saute sans saknussemm, comme la parité) ;
- le repli sur support faible, et le fait qu'une ligne absente du cache
  **lève** au lieu de se replier en silence ;
- le support d'une ligne Fraktur, **entre 0,5 et 0,7** : le chiffre qui
  explique pourquoi le seuil n'a pas sauvé les deux frontières qui ont
  réfuté H1.

**Et un test a trouvé une régression que j'avais introduite.** Le garde
d'échelle, deuxième version : en élargissant la tolérance à 0,30 pour tuer un
faux positif, j'avais tué le vrai positif avec. Il ne refusait plus les
dixièmes de millimètre — la trappe pour laquelle il avait été écrit.

Le fond est plus profond que le réglage. Sans `WIDTH` de page déclaré,
l'étendue des lignes donne **1,181 pour `37-GT-BNL`** (vraie échelle 1,181)
et **1,247 pour Gallica** (vraie échelle 1,0). L'heuristique ne peut pas les
distinguer. Le garde ne devine donc plus : quand la page ne déclare pas sa
largeur, il **exige `--scale`** et refuse sinon. Vérifié sur les deux corpus
réels.

`LICENSE` réparé (le `curl` initial avait échoué en silence).

Campagne relancée : verdict identique, **H1 réfutée**. Reproductible.

**La file est vide de tout ce qui ne demande pas d'arbitrage.** Ne restent
que l'épingle de budget de `rewrite_alto_file`, H2 (type **C**), et la PR de
la branche saknussemm. La boucle s'arrête sur « l'item suivant exige une
décision humaine ».

## 2026-09-23 — H11 : le réordonnancement n'existe pas, et les pixels savent apparier

Deux questions ouvertes par H10, fermées par la mesure. Rapport : `docs/H11.md`.

**Le cas manquant était nommé dans H10** : ses neuf pages sont en une seule
colonne, donc l'hypothèse de monotonie du recollage au caractère n'avait
jamais été testée là où elle est fragile. *Le Temps*, 5 janvier 1890, six
colonnes. Une lecture en trame produirait 41 % d'inversions. Mesuré :
**0,03 % (medium) et 0,18 % (small)**, et **toutes** remontent à deux lignes
d'un ou deux mots que l'appariement de la mesure confond — pas le modèle.

Ce qui arrive vraiment sur une bande dense est le **décompte** : 298 lignes
rendues pour 284. Le mode de défaillance que le caractère absorbe et que le
Jaccard refuse. **La réserve de H10 tombe pour ce cas**, et seulement pour
lui : un producteur qui demanderait une *transcription* sans donner les
lignes rendrait l'ordre au modèle, et rien ici ne le mesure.

**Le défaut de `min_source_similarity` a une sortie, et ce n'est pas un
seuil.** Les deux questions qu'il confond n'ont pas besoin de la même
preuve : la plausibilité se juge contre le texte, l'attachement contre les
pixels. Mesuré en dégradant la source jusqu'à 45 % : le recouvrement des
deux populations passe de 0 % à **70 %** côté texte — plus aucun seuil ne
sépare — et reste à **11 %** côté pixels, dont la médiane sur les lignes
correctes ne bouge pas (0,95 → 0,94). Le signal ne dépend pas de la qualité
de la source.

Réserve écrite au rapport : j'ai bruité le **texte**, pas l'**image**. Le cas
d'un scan abîmé, où le CTC souffrirait aussi, n'est pas mesuré.

La forme que prendrait le garde d'attachement est une extension de surface
publique de saknussemm — **type C**, arbitrage du mainteneur. Elle part dans
`## Questions`, pas dans la file.

### 2026-09-23 — H12 : zéro ligne mal rattachée, la sûreté vient du veto, pas du canal

Le mainteneur a tranché : aucune ligne mal rattachée, même contre un gain.
Le recours de H11 §3 est retiré. Rapport : `docs/H12.md`.

**La cause est lue, pas supposée.** Sur la bande du *Temps*, `small` rend
284/284 et décale seize lignes : une ligne parasite `«` supprimée, une ligne
coupée en deux seize lignes plus loin. Compte exact, position fausse.

**Les entiers dans le flux ne protègent de rien** — le modèle renumérote en
comptant (20 et 142 lignes sous le mauvais numéro). **Les ID ALTO opaques
tiennent** : zéro sur les deux modèles, il les recopie.

**Le veto par marge** — plancher 0,35 *et* 0,15 d'avance sur toute autre
ligne de la page — laisse passer zéro ligne mal rattachée sur toutes les
campagnes (jugé par un critère indépendant), et zéro sur 126 échanges
délibérés jusqu'à 75 % de bruit OCR. Le prix : 5 % de refus sur OCR propre,
55 % à 60 % de bruit. Les pixels n'ajoutent rien en veto : la bibliothèque
reste sous `I4`.

Deux items de type **C** en questions ouvertes ; rien de plus à faire sans
arbitrage.

### 2026-09-23 — H12 §6 : comparé contre la VT, le zéro tient et coûte 0,5 point

9 pages d'OCR17+, `medium`. H12 (image + ID dans le flux + veto) : **CER
4,58 %, zéro ligne mal rattachée vérifiée contre la VT**, contre 8,55 % sans
rien faire. À égalité avec le recollage au caractère sous le même veto
(4,61 %), mais sans perdre une ligne là où la page nue en perdait 10. Les
systèmes sans veto qui infèrent l'identité ont laissé passer 2 (Jaccard) et
1 (small opaque) lignes ; le veto les refuse toutes.

Les 12 refus sont 12 bonnes corrections perdues, toutes des lignes jumelles
(noms de personnages, vers répétés). Une exemption de principe — la marge
n'est exigée que contre des voisines distinguables — rend la moitié du prix
(CER 4,31 %) en gardant zéro sur les trois jeux. Dessinée après avoir vu les
échecs : option mesurée, pas défaut, jusqu'à confirmation sur un corpus
neuf.

### 2026-09-23 — H13 §1 : le zéro sur de l'OCR réel (HIPE, 1 824 lignes, 30 titres)

HIPE-OCRepair 2026, `impresso-snippets` fr, texte seul, `medium`. H12 avec
veto : **CER 3,83 % → 2,36 %, zéro ligne mal rattachée contre la VT**, 14
refus sur 738 changements. Le Jaccard nu en laisse passer **8** — quatre
fois plus que sur OCR17+ : les lignes de presse se ressemblent. Le zéro
tient à tous les niveaux de bruit réel (jusqu'à 14 %).

Deux faux positifs du contrôle automatique inspectés : une espace insérée
avant un mot dont la VT est en capitales (contrôle sensible à la casse — à
corriger), et une hallucination sur un titre en bouillie que le veto
refuse. Aucun des deux n'est un rattachement.

NewsEye (8 pages BnF, 5 493 lignes, images) : Tesseract en cours pour
l'OCR source ; campagne vision H12 ensuite.

### 2026-09-23 — H13 §2–3 : NewsEye, le modèle apparie par l'image ; identifiants peints

5 111 lignes, image + OCR Tesseract réel. Avec un bon découpage, H12 à
identifiants opaques s'effondre quand même : **39 % de CER, 1 746 lignes
sous le mauvais identifiant** — le VLM transcrit l'image de haut en bas et
remplit les cases, dès qu'une ligne non envoyée est visible ou que la
source est fragmentaire. Le canal d'identité ne tient que si image et
texte se correspondent un pour un.

Réponse : **l'identité dans l'image** — composite de lignes recadrées,
identifiant peint à gauche. Dérive divisée par dix (182), refus par quatre
(415), **CER 11,26 % → 8,03 %** avec veto, 3 résiduelles dont aucune n'est
le texte d'une autre ligne. Le prix du zéro est concentré sur les 212
lignes en bouillie (33,8 % sans veto, 80 % avec).

Fusion ancres+caractères : gain modeste (HIPE 2,41 %), ne sauve pas la
transcription. Repli ligne à ligne : 77 % repassent le veto, zéro mal
rattachée, CER inchangé — sûr, pas rentable.

Trois lanceurs refusés avant envoi (découpages) et un tué par la mémoire
(8 pages pleine résolution en cache) ; corrigé : image ouverte par bloc,
sauvegarde incrémentale, reprise.

### 2026-09-23 — H14 : recouper un paragraphe brut — texte, décompte, pixels

Question du mainteneur : reconstruire les lignes depuis un paragraphe
brut, par décompte de mots ou par le CTC. Mesuré sur NewsEye (5 111
lignes, CTC de toutes les lignes). Décompte de mots : 85 % de CER,
mort-né. Pixels > texte OCR comme référence, surtout sous bruit (30,8 %
contre 37,6 % à 20–50 %). Référence « tout ce qui est visible dans le
recadrage » : −11 points sans veto, **9,70 %** sous veto — mais toujours
derrière les identifiants peints (8,03 %) : recouper après coup vaut
moins qu'empêcher la dérive. Le CTC reste en secours et en géométrie.
