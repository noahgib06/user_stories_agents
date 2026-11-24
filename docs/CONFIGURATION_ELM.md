# Configuration ELM

## Principe de sécurité
- Commencer **uniquement sur un projet ELM de recette**.
- Compte technique dédié, droits minimaux : création/modification d'artefacts de test (Test Plan/Case/Script/Suite/Execution Record), aucun droit d'administration.
- Aucun secret dans le dépôt : identifiants par variables d'environnement.

## Étapes
1. `cp config/elm.example.json config/elm.json` (ignoré par git).
2. Renseigner `base_url`, `project_area`, `allowed_project_areas`, `requirement_base_url`.
3. Renseigner `creation_factories` : URL des fabriques de création QM de **votre** projet (récupérables via le catalogue de services OSLC QM : `<base_url>/oslc_qm/catalog`). Les valeurs `XXXX` de l'exemple sont à remplacer ; une fabrique doit être sur le même hôte que `base_url`.
4. Optionnel : `auth_url` (JAS form-login), `suite_group_by` (`function|sprint|campaign|module`), `plan_by` (`campaign` ou `software_version`), `link_predicates` (surcharge des prédicats OSLC).
5. Environnement :
```bash
export ELM_ENV=recette
export ELM_USER=<compte technique>
export ELM_PASSWORD=<mot de passe>
```
6. `python3 -m ivq publish` (dry-run), contrôler `workspace/elm_out/` et `workspace/publish_report.json`, puis `--confirm`.

## Garde-fous appliqués par le code
Refus si : projet hors `allowed_project_areas` ; URL contenant un mot de `forbidden_url_substrings` (`prod`, `production`) ; `ELM_ENV` ≠ `recette` ; identifiants absents ; HTTP non local ; fabrique hors hôte `base_url`.

## Artefacts créés
Test Plan (par campagne ou version logicielle), Test Case, Test Script (étapes, données, résultats attendus, préconditions), Test Suite (par regroupement choisi), Execution Records (`--with-executions`). Liens : Test Case → US/exigence (`validatesRequirement`), SSS/SSDD, macro-US ; Test Case → défaut (`relatedChangeRequest`).

## À valider sur votre instance
Le code suit OSLC QM 2.0 mais n'a été testé que contre un faux serveur. À contrôler sur le projet de recette : URL des fabriques, prédicats de liens, mapping des propriétés personnalisées `ivq:*` vers vos attributs ELM, mode d'authentification (Basic, JAS form ; OAuth non supporté), gabarits de projet obligatoires. Ajustez `link_predicates` si vos liens ne s'affichent pas.
