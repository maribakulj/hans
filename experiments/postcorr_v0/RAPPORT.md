# Post-correction sans décodeur V0 — rapport (phase 4)

Données : HIPE-OCRepair-Bench v0.9, français (icdar2017 + impresso-snippets), re-découpé par groupe documentaire ; pseudo-lignes de 50-80 caractères ; **test : 3 108 lignes, 49 groupes** (propre 1 583 / modéré 1 410 / lourd 115). Tous les réglages sur dev, test évalué une fois. IC 95 % par bootstrap sur les groupes. CPU seul (pas de GPU) : budgets d'entraînement réduits et déclarés (S2 3 époques, S3 2 époques).

## Réduction relative du CER (test) et taux de lignes dégradées

| système | global | propre (CER 0,47 %) | modéré (5,90 %) | lourd (19,2 %) | lignes dégradées (global / propre) | coût CPU / 1 000 lignes |
|---|---|---|---|---|---|---|
| S0 identité | 0 | 0 | 0 | 0 | 0 / 0 | 0 |
| S1 canal bruité | −2,9 % [1,9 ; 3,9] | −1,6 % | −3,4 % | −1,5 % | 1,0 % / 0,4 % | 6,6 s |
| **S2 étiqueteur (CANINE)** | −8,6 % [5,9 ; 13,3] | −10,1 % | −8,8 % | −7,0 % | **0,13 % / 0,13 %** | 125 s (2 fils) |
| S3 ByT5-small libre | −20,2 % [17,3 ; 26,1] | −15,9 % | −25,0 % | −2,4 % [−9,9 ; 17,4] | 7,4 % / 5,1 % | 314 s (4 fils) |
| **S4 ByT5 contraint** | **−23,6 %** [19,9 ; 28,6] | −15,9 % | **−26,6 %** | −14,2 % | 7,0 % / 5,1 % | ≈ S3 |
| S6 routeur (S0/S2/S4) | −13,1 % [10,1 ; 17,8] | −8,1 % | −13,6 % | −12,9 % | 1,6 % / 0,13 % | ≈ 0,3 × S3 + S2 |
| S5 LLM (Sonnet, 150 lignes) | −45 % (échantillon) | +43 % | −55 % | −43 % | 13 % / **18 %** | appels API |

Éditions (test) : S2 725 utiles / 4 fausses ; S3 2 350 / 653 ; S4 2 325 / 341 ; S6 1 239 / 138. Routage S6 : 969 lignes → S0, 1 867 → S2, 272 → S4. Estimateur de CER : Spearman 0,75 (test) ; 35 % des lignes modérées classées propres.

## Verdicts (seuils figés le 01/10)
- **H1 — infirmée.** Sur le bruit modéré, S2 obtient 35 % de la réduction de S3 (−8,8 % contre −25,0 % ; seuil 80 %). Sa dégradation est bien inférieure (0,14 % contre 8,7 %) et il est plus rapide (125 s avec 2 fils contre 314 s avec 4 fils, soit ≈ 5× par fil), mais le gain manque.
- **H2 — confirmée.** Strate propre : S2 0,13 % et S6 0,13 % de lignes dégradées (< 1 %) ; S3 5,1 % et S5 18 % (> 1 %).
- **H3 — infirmée.** Strate lourde : S4 corrige davantage que S2 (−14,2 % contre −7,0 %, IC qui se chevauchent : [8,0 ; 21,9] / [3,4 ; 12,8]) mais dégrade 19,1 % des lignes contre 0 % (tolérance + 2 points). Puissance faible (115 lignes, 20 groupes).
- **H4 — infirmée.** S6 (−13,1 %) ne domine ni S3 (−20,2 %) ni S4 (−23,6 %) en CER global ; il est en revanche moins cher que S3 (seules 272 lignes sur 3 108 passent par ByT5) et dégrade 4,5 fois moins de lignes.
- Gate de la phase 2 (« si H1 et H2 tombent, arrêt ») : seule H1 tombe — expérience menée jusqu'au bout.

## Ce que montrent les résultats
1. **Le compromis fidélité/gain existe bien** : S2 est le seul système quasi inoffensif (4 éditions fausses sur 3 108 lignes), mais ne corrige qu'un dixième du bruit ; S3/S4 corrigent un quart du bruit au prix de 5 % de lignes propres dégradées ; S5 corrige la moitié et dégrade 18 % des lignes propres.
2. **Normalisation indue** (question ouverte 5) : 28 % des lignes dégradées par S3 (29 % pour S4) le sont par la suppression d'un trait d'union de césure que la vérité terrain conserve (« con-cerne » → « concerne ») — exactement le risque décrit au §1 du protocole. Une contrainte « ne jamais supprimer ¬/- en fin de mot coupé » est l'amélioration la plus évidente de S3/S4.
3. **Le contrôle par budget (S4) aide sur le bruit lourd** (−2,4 % → −14,2 %) mais ne protège pas les lignes propres : le budget (CER estimé × longueur + 1) laisse passer les petites retouches. La contrainte figée de S4 était infaisable sur dev (déclaré).
4. **Le routeur est limité par l'estimateur** : 35 % des lignes modérées sont prises pour propres et laissées telles quelles.

## Limites
- CPU : S3 2 époques seulement, ByT5-small (pas base) ; S2 3 époques ; pas de n-best pour S4 ; pas de bruit synthétique (phase 3 optionnelle).
- Pseudo-lignes de 50-80 caractères (les unités HIPE n'ont pas de lignes) ; vérité terrain imparfaite (doublons, coquilles).
- S5 : un seul modèle, une seule consigne, 150 lignes.
- Chiffres non comparables au classement HIPE (re-découpage par groupe, imposé par la fuite possible des splits d'origine).

Exemples qualitatifs (10 réussites et 10 dégradations par système) : postcorr/EXEMPLES.md. Décisions datées : postcorr/DECISIONS.md.
