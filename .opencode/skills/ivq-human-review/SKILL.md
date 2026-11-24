---
name: IVQ Human Review
description: Point d'arrêt de validation humaine (IVQ/PO) avant publication ELM : tableau de revue, décisions, versions
---

## Principe
Aucun test n'est publié sans décision humaine. Les agents n'exécutent jamais `review-set` ni `review-apply`.

## Déroulé
1. `python3 -m ivq review-export` → `workspace/review.csv` (séparateur `;`).
2. Présenter : tableau (id, US, type, priorité, statut), synthèse de `workspace/coverage.md`, constats de `workspace/quality_notes.md`.
3. Demander à l'humain de décider, puis s'arrêter :
   - `python3 -m ivq review-set <ID> Validé|Rejeté|Brouillon --by "<Nom>" [--comment "..."]` (commentaire obligatoire pour `Rejeté`) ;
   - ou renseigner `status`, `reviewer`, `comment` dans `review.csv` puis `python3 -m ivq review-apply workspace/review.csv`.
4. Un test modifié (nouvelle version) retombe en `Brouillon` : la validation ne vaut que pour la version relue.
