---
name: IVQ Story Format
description: Format normalisé des fiches User Story / fonction de service (stories.json) et règles d'ingestion CSV, Excel, Word, DOORS Next, GitLab
---

## Fiche structurée (`workspace/stories.json`)

```json
{"id":"US-101","title":"...","version":"2","priority":"P1","service_function":"FS-AUTH-LOGIN","actor":"...",
 "preconditions":[],"business_rules":["RG1: ..."],"inputs":["login (3-20 car.)"],"expected_result":"...",
 "alternatives":[],"errors":[],
 "acceptance_criteria":[{"id":"US-101-AC1","text":"..."}],
 "source":{"type":"csv|xlsx|doors|word|gitlab","ref":"..."}}
```

Champs obligatoires : `id, title, version, priority, service_function, acceptance_criteria`. Les critères ont un id stable `<US>-AC<n>`.

## Sources
- CSV/Excel : en-têtes FR/EN reconnus (voir `ivq/ingest.py`) ; listes en cellule séparées par ` | ` ; critères `AC1: texte | AC2: texte`. Exemple : `examples/stories.csv`.
- Word / DOORS Next : extraire id, version, priorité, fonction de service et critères tels quels ; un macro-US se découpe en US filles avec un champ `parent` si la source le donne.
- GitLab : issues → brouillons marqués `needs_enrichment`.

## Règles
- Ne jamais inventer une règle, une borne ou une valeur : champ vide + question pour le PO.
- Conserver l'identifiant et la version sources pour la traçabilité.
