# Sécurité et données

## Flux de données
| Donnée | Où | Sortie du poste ? |
|---|---|---|
| Sources (`sources/`) | local, ignoré par git | **Oui, vers le fournisseur LLM** quand un agent les lit |
| `workspace/` (fiches, tests, journal, prompts) | local, ignoré par git | Oui pour ce que lit l'agent (LLM) |
| Publication ELM | votre serveur ELM | Uniquement vers `base_url` (recette) |
| GitLab | `GITLAB_URL` | Lecture seule via `GITLAB_TOKEN` |

Le CLI `ivq` n'appelle aucun service tiers hors ELM et GitLab.

## Avant d'utiliser des données client
1. Faire valider par le client le **fournisseur LLM** (région, rétention, non-entraînement) ou utiliser un modèle hébergé en interne.
2. Anonymiser/retirer les données sensibles des sources si la politique l'exige.
3. Les outils web (`webfetch`/`websearch`) sont refusés par `opencode.jsonc` ; ne pas les rouvrir.
4. Les agents n'ont accès qu'à leurs commandes `ivq` et fichiers `workspace/` ; `review-set`, `review-apply` et `link-defect` ne sont ouverts à aucun agent.

## Secrets
`ELM_USER`, `ELM_PASSWORD`, `GITLAB_TOKEN` : variables d'environnement uniquement. `config/elm.json`, `config/reviewers.json`, `.env`, `workspace/`, `sources/` sont dans `.gitignore`. Ne jamais commiter ces fichiers.

## Rétention et archivage
`workspace/` contient données client et journal d'audit. Par projet client : utiliser un dossier dédié (option globale placée avant la commande : `python3 -m ivq -w /chemin/client-X coverage`), archiver `journal.jsonl` + `prompts/` avec les livrables, vérifier `audit-verify` avant archivage, puis purger selon le contrat.

## Limites
- `--by` n'authentifie pas le relecteur (liste blanche déclarative).
- Le journal est protégé contre la modification par chaînage de hash, pas contre sa suppression complète : sauvegardez-le.
- Les sorties du LLM doivent toujours être relues avant validation.
