# Installation

## Prérequis
- Python ≥ 3.10 (le CLI `ivq` n'utilise que la bibliothèque standard).
- `openpyxl` uniquement pour lire des sources `.xlsx` et exporter les jeux de données en Excel : `pip install -r requirements.txt` (dans un venv si votre système bloque `pip`).
- opencode **V2** (préversion) : paquet npm `@opencode-ai/cli`, binaire `opencode2`. L'ancien binaire `opencode` (V1) refuse `opencode.jsonc` (champ `permissions`).
- Un fournisseur LLM configuré dans opencode (`opencode2 auth`). **Voir `SECURITE_DONNEES.md` avant de l'utiliser sur des données client.**

## Installation
```bash
git clone https://github.com/noahgib06/user_stories_agents.git
cd user_stories_agents
npm i -g @opencode-ai/cli        # fournit opencode2
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt   # optionnel (Excel)
```

## Vérification
```bash
python3 -m unittest discover -s tests -t .     # 17 tests (1 ignoré sans openpyxl)
opencode2 debug config                         # la configuration doit se charger sans erreur
opencode2 debug agents                         # 6 agents IVQ : ingestion, analyse, generation, couverture, adaptateur-elm, orchestrateur
```

## Premier lancement
```bash
opencode2        # agent par défaut : orchestrateur
/ivq-run examples/stories.csv
```
Sans LLM, la chaîne déterministe se teste avec les exemples (voir README).

## Dépannage
| Symptôme | Cause / action |
|---|---|
| `V2 permissions are not supported by OpenCode V1` | Vous lancez `opencode` (V1) : utilisez `opencode2`. |
| `ModuleNotFoundError: openpyxl` | `pip install -r requirements.txt`, ou fournissez un CSV/JSON. |
| `pip` refusé (PEP 668) | Utilisez un venv. |
| Commande shell refusée dans opencode | Normal : les permissions n'ouvrent à chaque agent que ses commandes (`opencode.jsonc`, `.opencode/agents/*.md`). |
| `publish` : « ELM_ENV=recette requis » | Voir `CONFIGURATION_ELM.md`. |
