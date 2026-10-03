# Post-correction OCR sans décodeur — protocole expérimental V0

Document de handoff pour une session Claude Code. À placer à la racine d'un dépôt vide (ou en `docs/PROTOCOLE.md`, avec un `CLAUDE.md` qui y renvoie). Le prompt de lancement figure en fin de document.

---

## 1. Contexte

La post-correction OCR par LLM décodeur réécrit plus qu'elle ne corrige. Elle génère une sortie libre, ce qui l'expose à l'hallucination, à la normalisation indue (orthographe ancienne modernisée, ponctuation réécrite), à la dérive de longueur et à la perte de l'alignement caractère à caractère avec la source. Elle coûte une génération complète même quand quelques caractères seulement sont faux, et elle dégrade des lignes qui étaient correctes.

L'hypothèse de travail est qu'un système qui traite la correction comme un **étiquetage d'éditions bornées**, avec un routage par régime de bruit et un générateur seq2seq réservé aux cas très dégradés, obtient un meilleur compromis fidélité/gain/coût. Ce système doit en outre produire des corrections locales et traçables, réinjectables dans l'ALTO sans reconstruction globale.

Cette V0 est une expérience autonome. L'intégration dans une chaîne de production existante (reconstruction ALTO, benchmark de pipeline) est hors périmètre. On exige seulement que la sortie de chaque système soit exprimable comme une liste d'éditions avec offsets dans la ligne source (voir §7).

## 2. Questions falsifiables

Les seuils ci-dessous sont proposés. Ils doivent être figés dans `docs/DECISIONS.md` **avant** la première évaluation sur le jeu de test, puis ne plus bouger.

- **H1 — Étiqueteur vs seq2seq sur bruit modéré.** Sur les lignes de CER initial entre 2 et 15 %, l'étiqueteur d'éditions (S2) atteint au moins 80 % de la réduction de CER de ByT5 libre (S3), avec une latence au moins 5 fois inférieure et un taux de dégradation au plus égal.
- **H2 — Innocuité sur les lignes propres.** Sur les lignes de CER initial inférieur à 2 %, S2 et le routeur (S6) ont un taux de dégradation inférieur à 1 %. S3 et S5 (LLM décodeur) dépassent ce taux.
- **H3 — Utilité du seq2seq contraint sur bruit lourd.** Sur les lignes de CER initial supérieur à 15 %, ByT5 contraint (S4) obtient une réduction de CER supérieure à celle de S2, avec un taux de dégradation au plus 2 points au-dessus de S2.
- **H4 — Routage.** Le routeur S6 domine chaque système pris isolément sur le CER global, à coût par ligne inférieur à S3.

Si H1 et H2 tombent, l'étiquetage d'éditions n'apporte rien de décisif et l'expérience s'arrête là (gate go/no-go, §6).

## 3. Données

### Sources candidates

Les licences et la composition exactes sont à vérifier avant téléchargement. Chaque décision est à consigner dans `docs/DECISIONS.md`.

- Jeux des compétitions ICDAR 2017 et 2019 sur la post-correction OCR (paires OCR/vérité terrain alignées, partie française prioritaire).
- Corpus de vérité terrain français ouverts recensés par HTR-United (imprimés anciens et modernes). Il faut les repasser par un OCR pour obtenir les paires si seule la GT existe.
- Toute paire OCR/GT interne fournie ultérieurement : prévoir un chargeur générique, sans rien supposer du format au-delà de « ligne OCR, ligne GT, identifiant de document, métadonnées optionnelles (date, police, confiance moteur) ».

### Préparation

- **Découpage par document, jamais par ligne**, en train, dev et test. Les lignes d'un même document ne doivent pas fuir d'un split à l'autre.
- **Alignement caractère** OCR→GT par Levenshtein (bibliothèques `edlib` ou `rapidfuzz`). Les lignes dont l'alignement est manifestement faux (ratio de longueur aberrant, CER > 60 %) sont écartées et comptées.
- **Stratification** par CER initial en trois strates : propre (< 2 %), modéré (2–15 %), lourd (> 15 %). Les effectifs par strate et par split sont rapportés.
- **Matrices de confusion** calculées sur train uniquement, à partir des alignements.
- **Bruit synthétique** (optionnel, phase 3) : on injecte dans du texte propre des erreurs échantillonnées depuis les matrices de confusion. Il ne sert qu'à augmenter train et n'est jamais utilisé en évaluation.

## 4. Systèmes comparés

- **S0 — Identité.** Aucune correction. Borne inférieure et référence du taux de dégradation.
- **S1 — Canal bruité.** Les candidats sont générés par token jusqu'à une distance d'édition de 2, pondérés par les matrices de confusion et filtrés par un lexique issu de train. Le scoring se fait par un modèle de langue caractère (KenLM, n-gramme 6) ou par un petit modèle de langue masqué. Aucun réseau génératif.
- **S2 — Étiqueteur d'éditions.** Un encodeur caractère ou byte (encodeur ByT5-small ou CANINE) prédit une étiquette par caractère source : `KEEP`, `DELETE`, `REPLACE_<c>`, `APPEND_<s>` (insertion après le caractère). Le vocabulaire d'opérations est restreint aux K éditions les plus fréquentes sur train, avec K choisi pour couvrir environ 95 % des éditions ; la couverture réelle est rapportée. Le système fait deux à trois passes itératives et applique un seuil de confiance par opération, réglé sur dev.
- **S3 — ByT5 libre.** Seq2seq byte-level (ByT5-small, puis base si le budget le permet) fine-tuné OCR→GT, en décodage glouton ou beam 4.
- **S4 — ByT5 contraint.** Même modèle que S3. Sa sortie est réalignée sur l'entrée et rejetée (retour à l'entrée) si la distance d'édition dépasse un budget proportionnel au CER estimé. Variante : les n-best sont reclassés par le score du modèle d'erreur de S1.
- **S5 — LLM décodeur (baseline).** Un LLM généraliste sollicité par prompt de correction, sur un échantillon stratifié si le coût l'impose. Il ne sert qu'à situer les autres systèmes et n'est pas optimisé.
- **S6 — Routeur.** Un estimateur de CER par ligne (tête de régression sur l'encodeur de S2, enrichie des confiances du moteur OCR si disponibles) oriente chaque ligne : propre → S0 ; modéré → S2 ; lourd → S4. Les seuils de routage sont réglés sur dev.

## 5. Métriques

Toutes les métriques sont rapportées globalement **et par strate**, avec des intervalles de confiance par bootstrap sur les documents.

- CER et WER après correction, et leur réduction relative par rapport à S0.
- **Taux de dégradation** : proportion de lignes dont le CER augmente après correction, calculée en particulier sur la strate propre.
- **Bilan des éditions** : éditions correctes, éditions fausses introduites, erreurs laissées. C'est l'équivalent précision/rappel au niveau de l'édition.
- **Dérive de longueur** : distribution de |len(sortie) − len(GT)|.
- **Coût** : latence par 1 000 lignes (CPU et GPU séparément), mémoire, coût API pour S5.
- **Couverture du vocabulaire d'éditions** (S2) et **taux de rejet** du contrôle de budget (S4).
- **Estimateur de CER** (S6) : corrélation de Spearman avec le CER réel et matrice de confusion des strates.

## 6. Plan d'exécution et gates

1. **Phase 0 — Socle.** Chargeurs, alignement, stratification, métriques, S0, tests unitaires sur l'alignement et le calcul des éditions. *Gate* : les statistiques des données sont produites et relues, puis les seuils de §2 sont figés dans `DECISIONS.md`.
2. **Phase 1 — Baselines sans apprentissage profond.** S1, puis S5 sur échantillon. *Gate* : les chiffres de S0/S1/S5 sont reproductibles avec une commande unique.
3. **Phase 2 — S2 et S3.** Entraînement, réglage des seuils sur dev, évaluation sur test. *Gate go/no-go* : on vérifie H1 et H2. En cas d'échec, on rédige le rapport et on arrête.
4. **Phase 3 — S4, S6, bruit synthétique.** On vérifie H3 et H4. L'apport du bruit synthétique fait l'objet d'une ablation.
5. **Phase 4 — Rapport.** `docs/RAPPORT.md` contient les tableaux par strate, les exemples qualitatifs (dix corrections réussies et dix dégradations par système) et le verdict pour chaque hypothèse.

## 7. Contrat de sortie commun

Chaque système implémente la même interface et renvoie, pour chaque ligne :

```python
@dataclass
class Edit:
    start: int        # offset dans la ligne source
    end: int          # exclusif ; start == end pour une insertion
    replacement: str
    confidence: float | None
    source: str       # identifiant du système

@dataclass
class Correction:
    line_id: str
    source_text: str
    edits: list[Edit]  # non chevauchants, triés
    # corrected_text est dérivé en appliquant les edits, jamais stocké seul
```

Pour les systèmes génératifs (S3, S4, S5), les éditions sont reconstruites par réalignement de la sortie sur la source. Ce contrat garantit la traçabilité et prépare une réinjection ALTO future au niveau des `String`.

## 8. Structure du dépôt

```
docs/
  PROTOCOLE.md      # ce document
  DECISIONS.md      # journal daté : seuils figés, choix de données, écarts au protocole
  RAPPORT.md        # produit en phase 4
src/postcorr/
  data/             # chargeurs, alignement, stratification, confusion
  systems/          # s0_identity, s1_noisy_channel, s2_edit_tagger, s3_byt5, s4_byt5_constrained, s5_llm, s6_router
  eval/             # métriques, bootstrap, rapports
  contract.py       # Edit, Correction, application des éditions
configs/            # une config par système et par expérience
scripts/            # prepare_data, train, evaluate, report
tests/
```

Environnement Python, gestion via `uv` ou `pip`, seeds fixées, configs versionnées. Chaque chiffre du rapport doit pouvoir être régénéré par une commande documentée.

## 9. Critères d'acceptation

- `pytest` passe, avec des tests couvrant l'alignement, l'extraction et l'application des éditions (aller-retour source + edits = cible sur train) et les métriques.
- Une commande unique régénère chaque tableau du rapport à partir des données préparées.
- Aucun hyperparamètre ni seuil n'est réglé sur test ; tout réglage se fait sur dev et est consigné.
- Chaque hypothèse reçoit un verdict explicite (confirmée, infirmée, non concluante) avec les chiffres qui le fondent.

## 10. Hors périmètre V0

Intégration dans une chaîne de production existante, reconstruction ALTO, retour à l'image par VLM, rescoring des treillis CTC du moteur OCR, HTR manuscrit, langues autres que le français. Ces pistes sont notées pour une V1 si le gate de phase 2 est franchi.

## 11. Questions ouvertes

1. Quelles sources de paires OCR/GT françaises sont réellement disponibles et sous quelle licence ? Le choix conditionne tout le reste.
2. Les confiances du moteur OCR sont-elles présentes dans les données ? Sinon, S6 repose sur l'estimateur seul.
3. Quel budget GPU est disponible ? Il décide entre ByT5-small et base, et de la taille de l'échantillon pour S5.
4. Quelle unité de traitement adopter : la ligne, ou une fenêtre de plusieurs lignes pour les césures ? V0 : la ligne, sauf décision contraire consignée.
5. Comment mesurer la normalisation indue au-delà du CER ? Piste : classer les éditions fausses introduites (graphie modernisée, ponctuation, casse).

## 12. Prompt de lancement

> Lis `docs/PROTOCOLE.md` en entier. Tu travailles phase par phase, dans l'ordre, sans anticiper sur les phases suivantes. Commence par la phase 0 : propose d'abord un plan de travail court et la liste des sources de données que tu comptes utiliser, avec leurs licences vérifiées, puis attends ma validation avant de télécharger quoi que ce soit. Consigne chaque décision datée dans `docs/DECISIONS.md`. Ne règle jamais rien sur le jeu de test. Si une étape du protocole te semble mal posée, signale-le et propose une modification plutôt que de t'en écarter silencieusement. À chaque gate, arrête-toi et présente les résultats avant de continuer.
