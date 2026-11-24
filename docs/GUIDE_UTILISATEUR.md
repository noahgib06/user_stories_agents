# Guide utilisateur

## Principe
Les agents (LLM) proposent ; le CLI `python3 -m ivq` (déterministe) valide, versionne, calcule la couverture, journalise et publie. **Rien n'est publié dans ELM sans validation humaine.**

Chaîne : Collecte → Structuration → Génération → Contrôle → **Validation humaine** → Publication ELM → Traçabilité.

## 1. Déposer les sources
Placez vos fichiers dans `sources/` (contenu ignoré par git). Formats : CSV (séparateur `;`), Excel, JSON, Word / export DOORS Next / texte (l'agent ingestion les convertit en JSON), GitLab (`ingest-gitlab`).

Colonnes reconnues (voir `examples/stories.csv`) : ID exigence, Titre, Type (`us`/`macro`), Parent, Version, Priorité, Fonction de service, Acteur, Préconditions, Règles métier, Données d'entrée, Résultat attendu, Cas alternatifs, Erreurs, Critères d'acceptation, Sprint, Campagne, Module, SSS, SSDD, Version logicielle.
- Listes dans une cellule : séparées par ` | `.
- Critères : `AC1: texte | AC2: texte`.
- Macro-US : `Type=macro`, ses US filles pointent vers elle via `Parent`.
- SSS/SSDD : référentiel `id;doc;title;url` chargé par `ingest-refs`.

## 2. Générer
Dans opencode2 : `/ivq-run sources/<fichier>`. Le pipeline s'arrête avant la validation. Résultats dans `workspace/` : `stories.json`, `model.json`, `tests.json` (tous en `Brouillon`), `coverage.md|json`, `journal.jsonl`.

Modèle de test imposé : `config/test-model.json` (statuts, priorités, types, catégories, nommage `TC-<US>-<NOM|ALT|ERR|LIM|SEC|PER|REG>-<NN>`). Toute proposition non conforme est rejetée au `merge`.

## 3. Relire (IVQ / PO)
```bash
python3 -m ivq review-export            # workspace/review.csv (tableau de revue)
python3 -m ivq review-set TC-US-101-NOM-01 Validé --by "Prénom Nom" --comment "..."
python3 -m ivq review-apply workspace/review.csv   # décisions en lot
```
Pour le lot : dans `review.csv`, renseigner `status` (`Validé`/`Rejeté`), `reviewer` (nom) et éventuellement `comment` ; les lignes sans `reviewer` sont ignorées.
Statuts : `Brouillon` / `Validé` / `Rejeté`. Une validation vaut pour **une version** : si le test change, il passe en version +1, l'ancienne est conservée dans `history`, et il retombe en `Brouillon`.
Option : `config/reviewers.json` (voir `reviewers.example.json`) limite les relecteurs aux rôles IVQ/PO. Sans ce fichier, tout nom est accepté.

## 4. Couverture et traçabilité
```bash
python3 -m ivq coverage    # critères couverts / en attente / non couverts, trous de matrice, doublons, ambiguïtés, anomalies
python3 -m ivq trace       # workspace/traceability.csv : US → fonction → test → statut → exécution → défauts
python3 -m ivq datasets [--xlsx]   # jeux de données par test (CSV, ou Excel)
```

## 5. Publier dans ELM
Voir `CONFIGURATION_ELM.md`. Toujours un **dry-run** d'abord :
```bash
python3 -m ivq publish                                 # dry-run : RDF dans workspace/elm_out/, aucun appel réseau
python3 -m ivq publish --confirm [--group-by sprint] [--with-executions] [--no-plan] [--no-suites]
```
Seuls les tests `Validé` pour leur version courante sont envoyés. Un test déjà publié est mis à jour (ETag) ; en cas de conflit, rien n'est écrasé.

## 6. Anomalies
Créez le défaut dans ELM, puis : `python3 -m ivq link-defect TC-... <url du défaut> --by "Prénom Nom"`. Il apparaîtra dans `trace` et sera relié lors de la prochaine publication.

## 7. Audit
`workspace/journal.jsonl` : chaque action (source + sha256, modèle, prompt archivé dans `workspace/prompts/`, décision humaine, version, utilisateur système, date, statut de publication), chaîné par hash. Contrôle d'intégrité : `python3 -m ivq audit-verify`.

## Limites à connaître
- `--by` est déclaratif : ce n'est pas une signature électronique.
- La création de défauts et la saisie de résultats d'exécution se font dans ELM.
- L'extraction Word/DOORS est faite par le LLM : relire les fiches (`stories.json`) avant de générer.
