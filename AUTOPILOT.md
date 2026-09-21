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

### 3. `G2` — `CTCForcedAlignmentResolver` — **bloqué par H1**

`kraken.align.forced_align` existe déjà et rend, par caractère, un couple
`(début, fin)` **déjà remis à l'échelle de l'image** plus une confiance
(`kraken/align.py:81-83`). Il n'y a pas de modèle à entraîner pour répondre à
H1 : il y a un appel à câbler.

⚠️ L'hypothèse à tester en premier dans G2 : les émissions d'un recognizer
restent-elles informatives sur du français ancien (ſ long, ligatures) ? Si
elles ne le sont pas, l'alignement dérive **silencieusement**.

### 4. `G3` — `alignment_confidence` — **bloqué par H1**

Le rapport vraisemblance du chemin forcé / décodage libre. **Pas** un verdict
« unmatched » : un alignement forcé trouve toujours *un* chemin, quitte à
écraser un mot dans deux frames. Le signal est un score bas, pas un échec
d'appariement.

### 5. `G4` — bout en bout — **bloqué par G2**

---

## Passe la main au mainteneur

Hors de portée de la boucle, et ce n'est pas un problème à contourner :

- **créer le dépôt distant** `hans` et pousser (compte GitHub) ;
- **un troisième corpus** pour H1, avec image et ALTO au mot ;
- publier `saknussemm` sur PyPI (débloquerait `[parity]` en CI).

---

## Questions ouvertes

- **La géométrie verticale.** Tout ici est horizontal. Un polygone par mot
  demande un masque d'encre (§9 du récapitulatif) et c'est un jalon qui
  n'existe pas encore. **C** — ne pas l'ouvrir sans arbitrage.
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
