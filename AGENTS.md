# Équipe d'agents IVQ — génération de tests pour ELM/Jazz

Chaîne de traçabilité : **User Story → fonction de service → cas de test → exécution → anomalie**.

## Espace de travail (`workspace/`, hors git)
`stories.json` (fiches structurées) · `model.json` (modèle de test fonctionnel) · `tests.proposed.json` (propositions)
· `tests.json` (référentiel versionné) · `coverage.json|md` · `review.csv` · `datasets/` · `elm_out/` · `journal.jsonl` (audit, chaîné par hash).

## Mode « fais ton boulot »
Une phrase suffit : l'orchestrateur appelle `python3 -m ivq next` (détecte `sources/`, tests manquants, revue en attente, publication) et enchaîne les étapes agents jusqu'au prochain point humain.

## Règles absolues
1. **Validation humaine obligatoire** avant toute publication ELM : seul un humain (IVQ/PO) passe un test à `Validé`/`Rejeté`
   (`python3 -m ivq review-set|review-apply`). Les agents n'exécutent jamais ces commandes.
2. Les agents n'écrivent **jamais** `tests.json`/`journal.jsonl` directement : ils passent par `python3 -m ivq merge` (statut forcé `Brouillon`, historique conservé, version incrémentée).
3. Modèle de test imposé : `config/test-model.json` (priorités, types, catégories, nommage `TC-<US>-<TYP>-<NN>`). Ne rien inventer hors modèle.
4. Chaque test référence `story_id`, `story_version`, `service_function`, `criteria_ids` (≥1), `generator{agent,model}`.
5. Ne jamais inventer de règle métier/valeur : si l'information manque, lister une question pour le PO plutôt qu'un test spéculatif.
6. ELM : projet de **recette** uniquement, dry-run par défaut ; `publish --confirm` seulement sur demande humaine explicite.
7. Aucun secret dans le dépôt (`ELM_USER`, `ELM_PASSWORD`, `GITLAB_TOKEN` via variables d'environnement).

## Format d'un test (`tests.proposed.json` → `{"tests":[...]}`)
Champs : `id, title, description, priority, type, category, owner, story_id, story_version, service_function, software_version,
criteria_ids[], preconditions[], steps[{action,data,expected}], data_rows[{...}], generator{agent,model}`.
Exemple : `examples/tests.proposed.json`. Fiche US (`stories.json`) : voir `examples/stories.csv` et `ivq/ingest.py`.
