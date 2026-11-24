---
name: IVQ Test Matrix
description: Matrice de génération de tests (nominal, alternatif, erreur, limite, sécurité, performance, régression), nommage et qualité des étapes
---

## Matrice
| Type | Code | Quand |
|---|---|---|
| nominal | NOM | toujours |
| erreur | ERR | toujours |
| alternatif | ALT | un cas alternatif est décrit |
| limite | LIM | une donnée a une borne ou un format (min-1, min, max, max+1) |
| securite | SEC | un acteur, un rôle ou une permission est impliqué |
| performance | PER | uniquement avec une exigence non fonctionnelle chiffrée |
| regression | REG | la US modifie une fonction de service existante |

La source de vérité est `config/test-model.json` (priorités, catégories, nommage).

## Nommage
- `id` : `TC-<US>-<CODE>-<NN>`, ex. `TC-US-101-NOM-01` ; `title` : `[<fonction de service>] <type> - <objectif>`.

## Qualité
- Un test = un objectif ; étapes atomiques et numérotées.
- `expected` observable et mesurable : pas de « correct », « rapide », « approprié », « etc. ».
- Données concrètes dans `data_rows` (valeurs aux bornes incluses).
- Pas de doublon : deux tests du même type sur la même US doivent différer par les données ou le flux.
- Chaque critère d'acceptation est couvert par ≥ 1 test via `criteria_ids`.
