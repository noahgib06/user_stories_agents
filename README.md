# IVQ Agents — tests issus de User Stories pour ELM/Jazz

Projet [opencode](https://opencode.ai) : une équipe d'agents génère des cas de test (US, macro-US, fonctions de service) destinés à ELM (Jazz) pour produire STD/STR.
Les agents raisonnent ; la partie déterministe (validation, versionnage, couverture, audit, publication OSLC) est dans le CLI Python `ivq` (stdlib, Python ≥ 3.10).

| Agent (`.opencode/agents/`) | Rôle | Prio |
|---|---|---|
| `ingestion` | Sources (CSV/Excel/Word/DOORS/GitLab) → `stories.json` | 0 |
| `analyse` | Acteurs, règles, bornes, flux → modèle de test + matrice | 1 |
| `generation` | Cas de test (nominal/alt/erreur/limite/sécurité/perf/régression), étapes, jeux de données | 0 |
| `couverture` | Traçabilité, trous, doublons, ambiguïtés → rapport | 2 |
| `adaptateur-elm` | Test Script / Case / Suite + liens OSLC (dry-run par défaut) | 3 |
| `orchestrateur` (primaire) | Pilote, arrêt de validation humaine, journal | 3 |

Configuration opencode v2 : `opencode.jsonc` (règles `permissions` ordonnées, la dernière correspondance gagne ; tout est refusé par défaut puis rouvert par agent),
agents Markdown (`mode`, `steps`, `permissions`), commandes `.opencode/commands/` et **skills** `.opencode/skills/<id>/SKILL.md` :
`ivq-story-format`, `ivq-test-matrix`, `ivq-human-review`, `ivq-elm-oslc` (chargés à la demande par les agents).

## Documents d'entrée
Déposez vos sources (CSV, Excel, Word, exports DOORS Next, JSON) dans `sources/` (contenu ignoré par git, rien n'est poussé), puis `/ivq-run sources/<fichier>`.

## Utilisation
```bash
opencode                      # agent par défaut : orchestrateur
/ivq-run examples/stories.csv # ingestion → analyse → génération → contrôle, puis arrêt
/ivq-review                   # tableau de revue (workspace/review.csv) + couverture
python3 -m ivq review-set TC-US-101-NOM-01 Validé --by "Prénom Nom"   # décision HUMAINE
/ivq-publish                  # dry-run ; /ivq-publish confirm => publication réelle
```
Sans LLM, la chaîne se teste avec les exemples :
```bash
python3 -m ivq ingest examples/stories.csv && python3 -m ivq merge examples/tests.proposed.json
python3 -m ivq coverage && python3 -m ivq review-export
cp config/elm.example.json config/elm.json && python3 -m ivq publish   # dry-run
python3 -m unittest discover -s tests -t .
```
Les listes dans une cellule CSV/Excel sont séparées par ` | ` ; critères : `AC1: texte | AC2: texte`.

## Garde-fous implémentés
- **Validation humaine** : `merge` force `Brouillon` ; `publish` n'envoie que `Validé` *pour la version courante* avec relecteur nommé.
- **Versionnage** : un test modifié incrémente `version`, snapshot dans `history`, retombe en `Brouillon`.
- **Traçabilité OSLC** : `validatesRequirement` + US/version/fonction/version logicielle/générateur/relecteur.
- **Modèle imposé** : `config/test-model.json` (priorités, types, catégories, nommage) vérifié à chaque `merge`/`validate`.
- **Recette uniquement** : `allowed_project_areas`, refus d'URL « prod », `ELM_ENV=recette`, `--confirm`, compte technique via `ELM_USER`/`ELM_PASSWORD` (permissions minimales côté ELM).
- **Audit** : `workspace/journal.jsonl` (source, décision, version, date, statut), chaîné par hash (`audit-verify`). Les permissions opencode limitent aussi chaque agent à ses commandes/fichiers ; `review-set`/`review-apply` ne sont autorisés à aucun agent.

## Documentation
- [`docs/INSTALLATION.md`](docs/INSTALLATION.md) — prérequis, opencode V2, vérification, dépannage
- [`docs/GUIDE_UTILISATEUR.md`](docs/GUIDE_UTILISATEUR.md) — du dépôt des sources à la traçabilité
- [`docs/CONFIGURATION_ELM.md`](docs/CONFIGURATION_ELM.md) — projet de recette, compte technique, fabriques OSLC
- [`docs/SECURITE_DONNEES.md`](docs/SECURITE_DONNEES.md) — flux de données, LLM, secrets, archivage

## Fonctions complémentaires
- **Macro-US** (`Type=macro`, `Parent`) : ligne de synthèse dans la couverture ; anomalies si parent inconnu ou macro sans enfant.
- **SSS / SSDD** : `ingest-refs examples/refs.csv` ; liens OSLC et option `require_sss`/`require_ssdd` dans `config/test-model.json`.
- **Traçabilité** : `trace` → `workspace/traceability.csv` (US → fonction → test → statut → défauts).
- **Publication ELM** : Test Plan, Test Script, Test Case, Test Suite (`--group-by function|sprint|campaign|module`), Execution Records (`--with-executions`), mise à jour avec ETag (conflit 412 = jamais d'écrasement), JAS form-login.
- **Défauts** : `link-defect <TC> <url>` (la création/résultat d'exécution se fait dans ELM).
- **Audit génération** : `merge --model --prompt-file --software-version` archive le prompt (sha256) dans `workspace/prompts/`.
- **Relecteurs** : `config/reviewers.json` (liste blanche IVQ/PO, voir `reviewers.example.json`).
- **Datasets** : `datasets [--xlsx]` (xlsx nécessite `pip install -r requirements.txt`).

## À valider chez vous
Testé : 14 tests unitaires/intégration (faux serveur ELM), config/agents chargés par `opencode2`. **Non testé** : un vrai ELM (URL des fabriques, prédicats OSLC, propriétés `ivq:*`, JAS/OAuth réel) et l'exécution LLM dans opencode. `--by` n'est pas une authentification cryptographique. Le modèle (`model:`) suit votre config opencode.
