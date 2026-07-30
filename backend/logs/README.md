# Logs chatbot (stats / coûts / qualité)

Chaque message utilisateur produit **une ligne JSON** dans un fichier du jour :

```text
backend/logs/chat_YYYY-MM-DD.jsonl
```

Les fichiers `*.jsonl` ne sont **pas** versionnés (gitignore). Ce dossier et ce README le sont.

## Activer

Rien à configurer : dès qu’un `POST /chat` réussit (ou échoue), une ligne est ajoutée automatiquement.

Console uvicorn : cherche `chat.event path=…`.

## Chemins (`path`)

| Valeur | Signification |
|--------|----------------|
| `deterministic` | Réponse catalogue Python, **0 token** LLM |
| `nlu` | Extract NLU (Claude → JSON), pas de dialogue |
| `dialog` | Dialogue LLM (tool loop), sans NLU |
| `nlu+dialog` | NLU puis dialogue LLM |

## Champs JSON (une ligne = un tour)

| Champ | Exemple | Usage stats |
|-------|---------|-------------|
| `ts` | ISO UTC | Timeline |
| `session_id` | uuid | Parcours |
| `partner_id` | `"1"` | White label |
| `path` | `deterministic` | % 0-token / coûts |
| `conv_state` | `presenting_list` | Tunnel |
| `route_kind` / `route_reason` | `pure_selection` / `…` | Routeur |
| `intent` | `select_indices` | Classifieur |
| `nlu_ran` / `nlu_intent` | `true` / `search` | Utilité NLU |
| `dialog_ran` | `false` | Dialogue LLM |
| `llm_used` / `llm_model` | modèle LiteLLM | Coût |
| `prompt_tokens` / `completion_tokens` / `total_tokens` | int | Facturation |
| `tools` | `["search_catalog"]` | Outils |
| `destination` | `Séville` | Popularité |
| `quote_ready` / `devis_ref` | bool / ref | Conversion devis |
| `latency_ms` | `45` | Perf |
| `user_msg_len` / `user_msg_preview` | 12 / `"Séville"` | Debug (preview tronquée 80 car.) |
| `reply_len` | 400 | Taille réponse |
| `error` | `null` ou message | Incidents |

## Exemple de ligne

```json
{"ts":"2026-07-30T15:30:00+00:00","session_id":"abc","partner_id":"1","path":"deterministic","conv_state":"awaiting_city_pick","route_kind":"continue","route_reason":"default","intent":"unknown","nlu_ran":false,"nlu_intent":null,"dialog_ran":false,"llm_used":false,"llm_model":null,"prompt_tokens":0,"completion_tokens":0,"total_tokens":0,"tools":["city_confirm","search_catalog"],"destination":"Séville","quote_ready":false,"devis_ref":"","latency_ms":38,"user_msg_len":7,"user_msg_preview":"Séville","reply_len":520,"error":null}
```

## Agrégats utiles (plus tard)

- % tours `path=deterministic`
- Somme `total_tokens` / jour / `partner_id`
- Top `destination`
- Taux `quote_ready` par session
- Latence moyenne

Script rapide :

```bash
cd backend
python -c "import json; from pathlib import Path
for line in Path('logs').glob('chat_*.jsonl'):
  ...
"
```

## Prod (évolution)

Même schéma → table Postgres `chat_events` ou export Datadog / CloudWatch.  
Ne pas logger le message utilisateur complet en clair hors démo interne (RGPD).

Module code : `agent/chat_logger.py`.
