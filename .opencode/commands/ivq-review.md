---
description: Présente le tableau de revue (Brouillon/Validé/Rejeté) et le rapport de couverture
agent: orchestrateur
---
Exécute `python3 -m ivq review-export`, puis résume `workspace/coverage.md` et le tableau de revue. Rappelle comment décider :
`python3 -m ivq review-set <ID> Validé|Rejeté --by <nom> --comment "..."` ou renseigner status/reviewer/comment dans `workspace/review.csv` puis `python3 -m ivq review-apply workspace/review.csv`.
