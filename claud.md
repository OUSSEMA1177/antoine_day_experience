# Day Experience AI — Guide de développement (claud.md)

> Document de référence pour piloter le développement étape par étape.  
> Basé sur le rapport de conception fonctionnelle et technique (Version F).

---

## Vision du projet

Agent IA conversationnel (pas un simple chatbot) pour les **partenaires B2B** de Day Experience : agences de voyage, tour-opérateurs, réceptifs.

L'agent doit :
- comprendre l'intention et mémoriser le contexte ;
- guider via le **tunnel conversationnel "Antoine"** ;
- rechercher des activités dans le catalogue ;
- recommander des expériences ;
- générer un **devis White Label PDF** ;
- consulter le statut de commandes (MVP : CSV) ;
- escalader vers un conseiller humain si nécessaire.

---

## Phase MVP (Stage) — Périmètre

| Inclus MVP | Reporté phase 2 |
|------------|-----------------|
| Dialogue naturel | Base de données relationnelle |
| Recherche activités (CSV) | API internes Day Experience |
| Tunnel découverte adaptatif | RAG / base vectorielle |
| Mémoire conversationnelle | Voucher / facture en temps réel |
| Génération devis PDF | WhatsApp / Teams |
| Page Web de démo | Intégration plateforme officielle |

---

## Architecture cible (Agent IA modulaire)

```
Utilisateur
    ↓
Frontend
    ↓
FastAPI (routes/)
    ↓
Orchestrator (agent/orchestrator.py)
    ↓
┌───────────┬────────────┬──────────────┬────────────────┐
│ Context   │ Catalog    │ Intent       │ Planner        │
│ Manager   │ Search     │ Detector     │                │
└───────────┴────────────┴──────────────┴────────────────┘
    ↓
Memory Manager + Tool Manager
    ↓
LiteLLM (Groq / Gemini / OpenAI / Claude…)
    ↓
Response Generator
    ↓
Utilisateur
```

**Principe** : le LLM comprend et dialogue ; `catalog_search` est la **source unique de vérité** pour les activités (pas de règles `if plage / if montagne`).

### Modules backend

| Module | Rôle |
|--------|------|
| `routes/` | Endpoints REST : `/chat`, `/activities`, `/orders` (+ `/quote` prévu) |
| `agent/orchestrator.py` | Chef d'orchestre — boucle LLM + tools |
| `agent/intent_detector.py` | Intention : recherche, devis, commande, FAQ, support… |
| `agent/planner.py` | Prochaine action : question, recherche, présentation, devis |
| `agent/context_manager.py` | Sync léger des slots depuis le message (profil, envies, durée…) |
| `agent/response_generator.py` | Post-traitement réponse (markdown, cohérence) |
| `search/catalog_search.py` | **Moteur catalogue** : requête → filtrage → scoring → Top K |
| `search/ranking.py` | Scoring activités (destination, budget, profil, thèmes) |
| `search/geo.py` | Alias géographiques, monuments, expansion mots-clés |
| `services/agent.py` | Re-export vers `orchestrator` (compat routes) |
| `services/data_loader.py` | Lecture CSV, cache — abstraction pour migration SQL/API |
| `tools/registry.py` | Tool calling : `search_catalog`, commandes, devis, escalade |
| `memory/` | Session + slots structurés + historique conversation |
| `prompts/` | System prompt, règles métier, tunnel Antoine |
| `pdf/` | Génération devis White Label (à faire) |
| `data/` | Fichiers CSV |

### Modules supprimés (migration agentique ✅)

| Ancien module | Remplacé par |
|---------------|--------------|
| `catalog_context.py` | `search/catalog_search.py` |
| `destination_resolver.py` | `search/geo.py` + `catalog_search` |
| `slot_extractor.py` | `agent/context_manager.py` (+ LLM phase 2) |
| `tunnel_guidance.py` | `agent/planner.py` + prompts |

### Évolution catalogue (sans refonte agent)

```
catalog_search.py
    ↓ (actuel)
  CSV via data_loader
    ↓ (Sprint 5)
  PostgreSQL
    ↓ (Sprint 6)
  API Day Experience
    ↓ (Sprint 7)
  Vector DB / RAG
```

---

## Étapes de développement

### Étape 0 — Structure du projet ✅

- [x] Arborescence `frontend/` + `backend/`
- [x] Fichiers squelettes Python
- [x] CSV vides avec en-têtes
- [x] `requirements.txt`, `.env.example`, `.gitignore`
- [x] Ce fichier `claud.md`

---

### Étape 1 — Données CSV

**Objectif** : peupler les fichiers dans `backend/data/`.

| Fichier | Contenu |
|---------|---------|
| `partners.csv` | id, nom_agence, email, logo_url, contact |
| `activities.csv` | id, destination, titre, description, prix, durée, langues, inclusions, catégorie, profil_cible |
| `destinations.csv` | id, nom, pays, région, description, saison_ideale |
| `faq.csv` | id, question, reponse, categorie |
| `orders.csv` | id, reference, partner_id, statut, date, activites, montant |
| `policies.csv` | id, activite_id, conditions_annulation, delai_remboursement |

**Collecte automatique B2B** (autorisée par le maître de stage) :

```bash
cd backend
# Copier .env.example → .env et renseigner B2B_LOGIN / B2B_PASSWORD
pip install -r requirements.txt
python scripts/scrape_b2b.py --max-destinations 3          # test rapide
python scripts/scrape_b2b.py --destinations 2222,4362    # Paris + Rome
python scripts/scrape_b2b.py --full                      # catalogue complet (long)
python scripts/scrape_b2b.py --full --resume             # reprend après coupure
```

En cas de coupure réseau (`Timeout`, `ConnectionReset`), le script :
- **réessaie** automatiquement chaque requête (5×)
- **sauvegarde** la liste activités dès la phase 1
- **checkpoint** tous les 25 détails dans `data/.scrape_checkpoint/`

Scripts :
- `backend/scripts/scrape_b2b.py` — catalogue B2B (activités, destinations, FAQ)
- `backend/scripts/import_partners_from_global.py` — partenaires depuis `data day experiencee.csv`

```bash
python scripts/import_partners_from_global.py
```

**Tâches** :
- [x] Script de collecte B2B (login → agent → ajax/liste → fiches produit → CSV)
- [x] `partners.csv` — 2921 partenaires extraits de `data day experiencee.csv` (colonne PARTNER)
- [x] `activities.csv` — ~2768 activités (scrape B2B)
- [x] `destinations.csv`, `faq.csv` — scrape B2B
- [ ] `policies.csv` / descriptions / inclusions — en attente (données non disponibles)
- [x] `orders.csv` — 1 ligne démo (`DEMO-001`) pour tests
- [x] `services/data_loader.py` — lecture + cache CSV + filtres + `search_activities_smart` + `recommend_activities`
- [x] Tests unitaires (`tests/test_data_loader.py`)

---

### Étape 2 — Backend FastAPI (base)

**Objectif** : API fonctionnelle sans LLM.

**Tâches** :
- [x] Configurer `main.py` (CORS, lifespan, health check `/health`, **frontend servi sur `/`**)
- [x] `app/config.py` — settings depuis `.env`
- [x] `routes/activities.py` → GET `/activities`, `/activities/{id}`, `/destinations`
- [x] `routes/orders.py` → GET `/orders/{reference}`
- [x] Modèles Pydantic dans `app/models.py`
- [x] Documentation auto Swagger `/docs`
- [x] Tests API `tests/test_api.py`

```bash
cd backend
uvicorn main:app --reload
# Swagger : http://127.0.0.1:8000/docs
```

---

### Étape 3 — Agent IA (LLM + LiteLLM) ✅

**Objectif** : boucle conversationnelle avec tool calling + réponses ancrées catalogue.

**Stack** : LiteLLM — modèle configurable via `.env` :
- Gratuit / dev : `groq/llama-3.3-70b-versatile`, `gemini/gemini-2.0-flash`
- Prod (plus tard) : `openai/gpt-4o`, `anthropic/claude-3-5-sonnet`, etc. — **même code**, changer `LLM_MODEL` + clé API

**Tâches** :
- [x] `agent/orchestrator.py` — orchestrateur principal (ex-`services/agent.py`)
- [x] `prompts/system_prompt.txt` + `tunnel_antoine.txt`
- [x] LiteLLM avec function calling (tools)
- [x] `routes/chat.py` → POST `/chat` `{ session_id, message }`
- [x] Gestion des erreurs LLM (timeout, rate limit, clé API manquante)
- [x] **Catalog Search** (`search/catalog_search.py`) — requête → filtrage → ranking → Top K *avant* le LLM
- [x] **Intent Detector** + **Planner** — prochaine action (question, résultats, devis)
- [x] **Anti-hallucination** — prix_net uniquement depuis le JSON injecté
- [x] Groq : tool-calling natif désactivé ; catalogue pré-injecté + réponse texte
- [x] Gemini / GPT / Claude : tool-calling natif activé + `search_catalog` en complément
- [x] Tests : `test_chat.py`, `test_tools.py`, `test_catalog_search.py`, `test_agent.py`, `test_conversation_scenarios.py`

```bash
# .env à la racine du projet
GROQ_API_KEY=...          # ou GEMINI_API_KEY=... ou OPENAI_API_KEY=...
LLM_MODEL=groq/llama-3.3-70b-versatile
# LLM_MODEL=gemini/gemini-2.0-flash
# LLM_MODEL=openai/gpt-4o-mini

cd backend
uvicorn main:app --reload
# Chat : http://127.0.0.1:8000/  |  Swagger : http://127.0.0.1:8000/docs
```

**Flux agent (actuel)** :
1. Réception message utilisateur
2. `context_manager` — sync slots léger + résolution destination si courte
3. `catalog_search` — requête texte + slots → filtrage → `ranking` → Top 20
4. `intent_detector` → `planner` — instruction ACTION MAINTENANT (une question/tour)
5. Injection `DONNÉES CATALOGUE` (JSON) dans le system prompt
6. Appel LiteLLM (tools natifs si modèle non-Groq)
7. Exécution tools si demandé (`search_catalog`, commande, FAQ…)
8. `response_generator` — post-traitement → historique

**Limitations connues (gratuit)** :
- Groq / Gemini free tier : erreurs 429 (quota saturé) → message « service saturé »
- Solution : attendre, changer de modèle, ou passer à une API payante (GPT-4, Claude)

---

### Étape 4 — Mémoire conversationnelle ✅ (MVP)

**Objectif** : contexte cohérent sur toute la session.

**Tâches** :
- [x] `memory/session_store.py` — stockage en mémoire (dict) pour MVP
- [x] `memory/conversation_manager.py` — historique messages (role, content)
- [x] `memory/memory_manager.py` — slots structurés
- [x] Extraction automatique des slots (`context_manager.py` — léger, extensible) :
  - `destination`, `profil_voyageur`, `envies`, `budget`, `taille_groupe`
  - `duree`, `dates`, `premiere_visite`, `seminaire`, `groupe_amis`
  - `destinations_exclues` (« je ne veux pas le Maroc »)
  - `partner_id` (message ou `POST /chat` + `?partner_id=` frontend)
  - `devis_ref`, `validite_jours` (7 j par défaut via `generate_quote`)
- [x] Ne pas redemander une info déjà connue (prompts + `planner.py` + tests)
- [x] Validation destination catalogue (`geo.resolve_destination_name`, rejet faux lieux)
- [ ] Short / Long / Session memory distinctes — structure prête, short seule en MVP
- [ ] Extraction slots avancée via LLM — reporté phase 2
- [ ] Redis / persistance multi-instance — reporté prod

---

### Étape 5 — Outils (Tools) ✅ (MVP)

**Objectif** : actions exécutables par l'agent.

| Tool | Description | Statut |
|------|-------------|--------|
| `search_catalog` | Recherche unifiée : destination, budget, profil, thèmes, query | ✅ |
| `search_activities` / `recommend_experiences` | Alias → `search_catalog` (rétrocompat) | ✅ |
| `get_activity_details` | Détail d'une activité par ID | ✅ |
| `get_order_status` | Statut commande par référence | ✅ |
| `generate_quote` | Génération PDF White Label | ✅ |
| `escalate_to_advisor` | Marque session pour conseiller humain | ✅ |
| `search_faq` | Recherche dans faq.csv | ✅ |

**Tâches** :
- [x] Schémas JSON des tools (OpenAI function format)
- [x] `tools/registry.py` — enregistrement centralisé + exécution
- [x] Fusion `search_activities` + `recommend_experiences` → `search_catalog`
- [x] Intégration avec `search/catalog_search.py`
- [x] Tests `tests/test_tools.py`

---

### Étape 6 — Génération devis PDF ✅ (MVP)

**Objectif** : devis White Label conforme au modèle Day Experience.

**Tâches** :
- [x] Librairie **ReportLab** (`requirements.txt`)
- [x] `pdf/quote_generator.py` — logo agence, activités, prix nets/publics, conditions
- [x] `routes/quote.py` → POST `/quote` + GET `/quotes/{filename}`
- [x] Tool `generate_quote` — génération PDF réelle
- [x] `ChatResponse.quote_url` — lien PDF renvoyé au frontend
- [x] Stockage PDFs dans `backend/output/quotes/`
- [x] Bouton téléchargement dans le frontend
- [x] Tests `tests/test_quote.py`

**Exemple API** (conversation Dubaï couple) :
```bash
curl -X POST http://127.0.0.1:8000/quote \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo",
    "partner_id": "1",
    "destination": "Dubaï",
    "activity_ids": ["50245", "39444", "39648"]
  }'
```

---

### Étape 7 — Frontend (page de démo) 🔄 (partiel)

**Objectif** : interface chat pour tester l'agent.

**Tâches** :
- [x] Page HTML/CSS/JS (`frontend/`)
- [x] Widget chat : zone messages, input
- [x] Appels API vers `POST /chat`
- [x] Gestion `session_id` (localStorage)
- [x] Frontend servi par FastAPI sur `http://127.0.0.1:8000/` (pas besoin de Live Server)
- [x] Messages d'erreur API affichés dans le chat
- [ ] Affichage des activités recommandées (cards structurées)
- [x] Bouton **Générer le devis PDF** (frontend) — `POST /quote/from-session`, sans appel Groq
- [x] `GET /session/{id}/quote-state` — activités catalogue sélectionnées, état bouton
- [x] Anti-simulation : filtre réponses « devis simulé / e-mail » + activités ancrées JSON
- [ ] Design responsive, charte Day Experience

---

### Étape 8 — Tunnel conversationnel "Antoine" ✅ (MVP)

**Objectif** : parcours guidé adaptatif pour créer un devis.

**Étapes tunnel** (internes — jamais exposées au partenaire) :
1. Destination (+ durée si connue) — ou proposition villes catalogue si envie thème (mer, Sahara)
2. Profil voyageur (couple, famille, groupe d'amis, solo, séminaire)
3. Envies / centres d'intérêt
4. Recommandations catalogue (titres + prix_net)
5. Sélection activités → devis PDF

**Tâches** :
- [x] Instructions tunnel dans `prompts/tunnel_antoine.txt` + `system_prompt.txt` (PDFs métier)
- [x] `agent/planner.py` — ACTION MAINTENANT : une question/tour, pas d'exposition « tunnel »
- [x] Saut d'étapes via mémoire slots
- [x] Thèmes sans destination : mer/plage, montagne, Sahara via `catalog_search` (recherche texte globale)
- [x] Anti-hallucination : pas d'activités/devis sans JSON catalogue (`context_has_activities`)
- [x] Tests scénarios : Maroc, Sahara, Paris, Tour Eiffel, groupe 20, Marrakech couple, plage (`test_conversation_scenarios.py`)

---

### Étape 9 — Escalade conseiller humain ✅ (MVP)

**Tâches** :
- [x] Règles d'escalade détaillées dans system prompt (remboursement, litige, hors catalogue, insatisfaction…)
- [x] Tool `escalate_to_advisor` + flag session
- [x] Produit hors catalogue → message explicite + suggestion escalade (ex. Corse Saleccia)
- [ ] Log des escalades (fichier ou table) — reporté phase 2

---

### Étape 10 — Tests et qualité ✅ (MVP)

**Tests fonctionnels** :
- [x] Recherche activités par critères (Paris, Maroc, Sahara, profil famille)
- [x] Anti-hallucination : Tour Eiffel, Corse, prix catalogue, plage sans destination
- [x] Mémoire : destination, exclusions, taille groupe, Marrakech 5j couple
- [x] Tunnel : `test_agent.py`, `test_context_manager.py`, planner
- [ ] Conversation fluide multi-tours E2E automatisée — manuel OK
- [ ] Génération PDF complète — étape 6
- [ ] Escalade E2E automatisée

**Tests techniques** :
- [x] pytest — **43 tests** (data_loader, API, chat, tools, catalog_search, geo, agent, scénarios, quote)
- [x] Tests API avec httpx TestClient

---

### Étape 11 — Déploiement démo

**Tâches** :
- [ ] Docker Compose (backend + frontend statique) — optionnel
- [ ] Variables prod dans `.env`
- [ ] Hébergement page de démo (Render, Railway, VPS…)
- [ ] README avec instructions complètes

---

## API REST — Récapitulatif

| Méthode | Route | Description |
|---------|-------|-------------|
| POST | `/chat` | Envoyer un message, recevoir réponse agent |
| GET | `/activities` | Liste/filtre activités |
| GET | `/activities/{id}` | Détail activité |
| POST | `/quote` | Générer devis PDF |
| GET | `/orders/{reference}` | Statut commande |
| GET | `/health` | Health check |

---

## Variables d'environnement

Fichier `.env` à la **racine du projet** (lu par `backend/app/config.py`).

```env
# --- LLM (un seul actif via LLM_MODEL) ---
GROQ_API_KEY=
GEMINI_API_KEY=
# OPENAI_API_KEY=          # futur : GPT-4o
# ANTHROPIC_API_KEY=       # futur : Claude

LLM_MODEL=groq/llama-3.3-70b-versatile
# LLM_MODEL=gemini/gemini-2.0-flash
# LLM_MODEL=openai/gpt-4o-mini
# LLM_MODEL=anthropic/claude-3-5-sonnet-latest

# --- API ---
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=true
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:5500,http://localhost:8000

# --- Scrape B2B ---
B2B_LOGIN=
B2B_PASSWORD=
```

**Changer de fournisseur LLM** : modifier `LLM_MODEL` + la clé correspondante, redémarrer uvicorn.  
L'architecture (orchestrator, catalog_search, tools, mémoire) reste identique.

---

## Conventions de code

- Python 3.11+
- Typage Pydantic v2
- Docstrings courtes sur services et tools
- Un fichier = une responsabilité
- Pas de logique métier dans les routes (déléguer à `agent/` et `search/`)
- Catalogue accessible via `search/catalog_search.py` → `data_loader` (abstraction pour SQL/API/RAG)

---

## Ordre de travail recommandé

```
0. Structure                         ✅
1. CSV + data loader                 ✅
2. API REST                          ✅
3. Agent IA modulaire (agent/)       ✅
4. Mémoire session                   ✅ MVP
5. Tools (search_catalog unifié)     ✅ MVP
6. PDF devis                         ✅ MVP
7. Frontend chat                     🔄 partiel (chat OK, cards PDF à faire)
8. Tunnel Antoine (planner)          ✅ MVP
9. Escalade + edge cases             ✅ MVP
10. Tests pytest                     ✅ MVP (43 tests)
11. Déploiement démo                 ⬜
```

### Migration architecture agentique (Sprints 1–4) ✅

| Sprint | Contenu | Statut |
|--------|---------|--------|
| 1 | Supprimer `catalog_context`, `destination_resolver`, `slot_extractor`, `tunnel_guidance` | ✅ |
| 2 | Créer `intent_detector`, `planner`, `catalog_search`, `ranking` | ✅ |
| 3 | Fusionner tools → `search_catalog()` | ✅ |
| 4 | Créer `response_generator` | ✅ |
| 5 | PostgreSQL derrière `catalog_search` | ⬜ |
| 6 | API Day Experience | ⬜ |
| 7 | RAG / Vector DB | ⬜ |

**Prochaine étape suggérée** : **Étape 7 — Frontend** (cards activités structurées, design responsive).

---

## Notes pour les sessions Claude / Cursor

Lors de chaque session de dev, indiquer :
1. **Étape en cours** (ex. « Étape 6 — PDF devis »)
2. **Tâches cochées / restantes** dans ce fichier
3. **Blocages** (données manquantes, quota LLM, template PDF…)

Mettre à jour les `[ ]` → `[x]` dans ce fichier au fur et à mesure.

### État au 25/06/2026

- **Architecture agentique** : `agent/` (orchestrator, intent, planner, context, response) + `search/` (catalog_search, ranking, geo)
- Plus de règles Python pour NLU — le LLM dialogue, `catalog_search` fournit la vérité catalogue
- Tool unifié `search_catalog` (destination, budget, profil, thèmes, query)
- Tunnel Antoine : une question/tour via `planner.py` + prompts
- Prompts alignés PDFs métier (Phase 1/2, escalade, white label)
- Frontend sur `http://127.0.0.1:8000/` — `?partner_id=1` pour white label
- **35 tests** pytest passants
- LLM : Groq/Gemini gratuits soumis à quotas (429) — APIs payantes compatibles via LiteLLM
- Prochaine évolution catalogue : SQL → API Day Experience → RAG (sans refonte agent)
