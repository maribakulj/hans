# Post-correction OCR sans décodeur — expérience V0

Expérience menée du 01/10 au 02/10/2026 dans une session de la boucle BBVLM, puis déplacée ici (la post-correction relève de l'écosystème saknussemm/hans, pas de BBVLM). Elle n'est **pas** branchée sur le code de `hans` ni sur sa boucle (`AUTOPILOT.md` inchangé).

- `PROTOCOLE.md` : protocole d'origine (systèmes S0-S6, hypothèses H1-H4).
- `DECISIONS.md` : journal daté (données, seuils figés, réglages sur dev, écarts).
- `RAPPORT.md` : résultats et verdicts (H1 infirmée, H2 confirmée, H3 et H4 infirmées).
- `EXEMPLES.md` : 10 réussites et 10 dégradations par système.
- `outils/` : préparation des données, contrat `Edit`/`Correction`, métriques, S1 à S6.
- `b0/` : statistiques, pseudo-lignes (dérivées de HIPE-OCRepair-Bench v0.9, CC BY-NC-SA 4.0 — usage non commercial, attribution, partage à l'identique), sorties et mesures.

Lien avec `hans` : le contrat de sortie (éditions avec offsets dans la ligne source) est celui dont `saknussemm` a besoin ; une édition qui change la segmentation (« dela » → « de la ») est exactement le cas que `hans` doit géométriser.

Chemins : les scripts référencent l'environnement de la session d'origine (`/tmp/...scratchpad`, venvs) ; à adapter pour une ré-exécution.
