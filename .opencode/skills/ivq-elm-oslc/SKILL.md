---
name: IVQ ELM OSLC
description: Publication des Test Script, Test Case et Test Suite dans ELM (OSLC QM) avec liens vers les exigences et garde-fous projet de recette
---

## Artefacts
- **Test Script** : étapes numérotées, données, résultats attendus, préconditions.
- **Test Case** : titre, description, priorité, type, catégorie, owner, `oslc_qm:validatesRequirement` → US, `oslc_qm:usesTestScript`.
- **Test Suite** : regroupement par fonction, sprint, campagne ou module (`--group-by`, `oslc_qm:usesTestCase`).
- **Test Plan** : par campagne ou version logicielle (`plan_by`) ; `--no-plan` pour l'omettre.
- **Execution Records** : `--with-executions`. **Défauts** : `link-defect` (humain) → `relatedChangeRequest`.
- **Liens** : US, SSS, SSDD, macro-US parente.
- Traçabilité portée par chaque artefact : US+version, fonction, version logicielle, générateur, relecteur, version du test.

## Garde-fous (appliqués par `ivq/elm.py`)
- Seuls les tests `Validé` par un humain pour leur version courante sont publiés ; pas de republication d'une même version.
- Projet dans `allowed_project_areas`, URL sans « prod », `ELM_ENV=recette`, compte technique `ELM_USER`/`ELM_PASSWORD`.
- Dry-run par défaut ; `--confirm` uniquement sur ordre humain explicite.

## Procédure
1. `python3 -m ivq publish` (dry-run) puis relire `workspace/publish_report.json` et `workspace/elm_out/`.
2. Après accord humain : `python3 -m ivq publish --confirm`.
3. Les URL des fabriques (`config/elm.json`) et les prédicats `ivq:*` sont à valider sur le projet de recette.
