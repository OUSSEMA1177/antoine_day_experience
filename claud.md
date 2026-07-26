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
┌────────────────────┬──────────────────────┐
│ Chemins déterministes│ Chemin LLM (Claude)   │
│ (0 token, catalogue) │ (NLU + dialogue)      │
│ • pays / continent   │ • envies floues        │
│ • thème + région     │ • reformulations       │
│ • support → e-mail   │ • « autre activité »   │
│ • ville hors catal.  │ • présentation activités│
│ • ask dest/profil    │                        │
│ • sélection / devis  │                        │
└────────────────────┴──────────────────────┘
    ↓
Tools (source de vérité catalogue)
  search_catalog · list_destinations · get_activity_details · …
    ↓
Memory + Quote State (sélection EXPLICITE seulement)
    ↓
Response (LLM formule à partir du JSON tool — pas d'invention)
```

### Principe d'architecture (important)

**Claude comprend le langage ; Python garantit le catalogue et le devis.**

| Responsabilité | Qui | Exemple |
|----------------|-----|---------|
| Comprendre formulations infinies / mixtes | **NLU (LLM → JSON)** | « 2e + une autre », « oui ajoute ceci » |
| Lister destinations / activités réelles | **Python + tools** | `list_destinations`, `search_catalog` |
| Ville hors catalogue courte (`toulouse`) | **Python** | 0 token, message clair |
| Appliquer sélection / append / devis | **Python** sur le JSON NLU | IDs, `awaiting_add_activity`, PDF |
| Confirmation devis | **Python** | dernière présentation / sélection (max 4), **jamais** tout `activites_discutees` |
| Choix « premier et quatrième » (pur) | **Python 0 token** | `parse_presentation_indices` |
| Inventer prix / villes / listes | **INTERDIT** | toujours tool ou JSON injecté |

**Anti-patterns à éviter**
- Détecter une « destination » sur une phrase multi-mots (`mix de tout`, `oui c est parfait`)
- Confirmer 40+ activités parce qu’elles matchent « pyramides » dans l’historique
- Laisser le LLM lister des destinations sans `list_destinations`
- Croire la réponse LLM (« 1 et 4 uniquement ») si `activites_selectionnees` n’a pas été mis à jour en Python
- **Court-circuiter le NLU** sur un message mixte (ordinal + « autre ») → devis trop tôt
- Empiler des regex infinies pour chaque reformulation — le NLU couvre le langage

**Chemins 0 token conservés** : continent/pays (`afrique`, `asie`), thème+région (`plage en Asie`), support e-mail, qualification tunnel (ask destination/profil/envies), ville catalogue exacte, hors-catalogue 1–2 tokens, **sélection/confirm purs** (`juste les deux premiers`, `oui c'est bon`).

### Workflow hybride (NLU → Python) — juillet 2026

```
Message partenaire
        │
        ▼
┌───────────────────────────┐
│ 0. intent_router          │  Matrice FERMÉE (1 intention dominante)
│    (priorité fixe)        │  support → not_chosen → raise_budget →
│                           │  need_place → search → country → selection
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ 1. Filtres 0 token        │  actions Python déterministes
└─────────────┬─────────────┘
              │ sinon (CONTINUE)
              ▼
┌───────────────────────────┐
│ 2. NLU (LLM → JSON)       │  langage flou / mixte seulement
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ 3. Python catalogue/devis │  IDs, append, PDF
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ 4. Dialogue LLM           │  dernier recours
└───────────────────────────┘
```

**Module** : `agent/intent_router.py` — `RouteKind` + `classify_route(message, slots)`.

| RouteKind | Exemple message | Action |
|-----------|-----------------|--------|
| `SUPPORT` / `SUPPORT_EMAIL` | remboursement, « votre e-mail » | e-mail support |
| `FAQ` | « taux de commission ? », « comment fonctionne la réservation » | réponse `faq.csv` (0 token) |
| `CITY_CONFIRM` | « oui » après « explorer Parc Kruger ? » | set destination + activités |
| `NOT_CHOSEN_YET` | « non pas encore » | aide région/thème/villes |
| `RAISE_BUDGET` | « augmentez budjet » | clear budget + re-search (≠ faux lieu) |
| `NEED_PLACE_FOR_SEARCH` | « budget 400 donne activités » sans lieu | noter budget, demander zone |
| `SEARCH_ACTIVITIES` | idem + `region_interest` / destination | `catalog_search` immédiat |
| `COUNTRY_OR_CONTINENT` | « Afrique », « Espagne » | listes / activités (+ fallback hors budget) |
| `PURE_SELECTION` | « juste les deux premiers », « oui », « 2e + autre », « ajoute ceci » | `quote_state` (0 token) |
| `CONTINUE` | reste | NLU → planner → LLM |

**Anti whack-a-mole** : ajouter un scénario dans `tests/test_scenario_router.py` pour chaque nouveau cas — pas un patch isolé.

**QA** : bouton **Nouveau** dans le widget → `DELETE /session/{id}` + nouveau `session_id` (évite slots fantômes au reload).

| Message | Chemin | Résultat |
|---------|--------|----------|
| `juste les deux premiers` | 0 token (pur) | sélection [1,2] → « préparer le devis ? » |
| `la 2e et une autre activité` | 0 token (`select_and_add`) | sélection #2 + ask thématique (pas devis) |
| `1 est ok vous avez d autre activite ?` | 0 token (`select_and_add`) | sélection #1 + ask thème (pas re-search) |
| `oui ajoute ceci` | 0 token (`add_this`) | **append** à la sélection → « préparer le devis ? » |
| `oui` (après ask devis) | 0 token (pur) | génère PDF avec les IDs session |
| `budget 400 + activités` (sans lieu) | routeur `NEED_PLACE` | budget noté, demande ville/zone |
| `AUGMENTEZ BUDJET` | routeur `RAISE_BUDGET` | plafond levé + re-search |
| `AFRIQUE` + budget trop bas | pays + fallback | options les moins chères |
| `quel est le taux de commission ?` | routeur `FAQ` | réponse `faq.csv` (0 token) |
| `Afrique du Sud` → `oui` | `awaiting_city_confirm` | destination Parc Kruger + activités |

### Évolution : ancien vs nouveau flux LLM

| Aspect | Ancien (Étape 3 initiale) | Actuel (juillet 2026) |
|--------|---------------------------|------------------------|
| Compréhension | Surtout le dialogue LLM | **NLU JSON** dédié + regex filet (`quote_state`) |
| Réponses simples | Passait quasi toujours par le LLM | **0 token** (Afrique, support, tunnel, sélection pure) |
| Sélection activités | Souvent interprétée par le LLM | **NLU flags** + `quote_state` Python (IDs, cap 4) |
| Messages mixtes | Regex / bugs devis trop tôt | **Routeur + regex** (append / autre activité) ; NLU si langage flou |
| Thèmes (plage, sahara) | Recherche texte fragile | **`themes.py`** + word boundaries (`mer` ≠ Merzouga) |
| Profil voyageur | Filtre dur possible | **Soft boost** dans `ranking` (plus d’exclusion) |
| Escalade | Tool + formulation LLM | **`support_policy`** — e-mail fixe, 0 token |
| Tokens / message | ~2–3k systématique | **0 à ~3k** selon le chemin (badge frontend) |
| Rôle orchestrateur | Envoie presque tout au LLM | **Arbitre** : 0 token → NLU → Python → dialogue |

**Ancien flux simplifié** : message → `context_manager` → `catalog_search` → `intent_detector` → `planner` → injection JSON → **1 appel LLM** → réponse.

**Nouveau flux** : message → Python 0 token (évident) ? → **NLU extract** (langage) → Python applique JSON → `intent` + `planner` + `catalog_search` → **dialogue LLM** seulement si nécessaire.

### Extracteur NLU structuré (`agent/nlu_extractor.py`)

Avant l’action catalogue/devis sur le langage flou, Claude renvoie un **JSON d'intention** (`prompts/nlu_extract.txt`) :

- Config : `LLM_NLU_EXTRACT=true` (défaut). Skip : saluts, pays/continent 0 token, hors-catalogue, **sélection/confirm/append** détectables en regex, routes 0 token.
- Helper : `is_pure_selection_or_confirm_message` — sépare sélection/confirm purs ; `intent_router` couvre aussi `select_and_add` / `add_this`.

**Input NLU** : prompt `nlu_extract.txt` + mémoire session (destination, profil, envies, taille_groupe) + message partenaire.  
**Output NLU** (JSON) : `intent`, `destination`, `continent`, `country`, `profil`, `taille_groupe`, `envies[]`, `confirm_selection`, `wants_another_activity`, `add_this_activity`, `selection_indices[]`, `reject_hint`, `is_place_name`, `mix_all_envies`, `confidence`.  
Injecté dans le dialogue comme bloc `NLU STRUCTURÉ` ; appliqué en session via `apply_nlu_to_session` ; **sélection/devis** via `_try_activity_confirmation(..., nlu=)`.

| Cas message | Output typique | Action Python |
|-------------|----------------|---------------|
| `Caire` / typo lieu | `destination`, `is_place_name: true` | active destination catalogue |
| `groupe de 6 amies` | `profil: groupe_amis`, `taille_groupe: 6` | slots |
| `sahara` / `mix de tout` | `envies[]`, évent. `mix_all_envies: true` | recherche |
| `plage en Asie` | souvent 0 token avant NLU ; sinon `envies: [mer]`, `continent: asie` | thème+région |
| `oui c'est bon` | skip NLU (pur) ou `confirm_selection: true` | devis si `awaiting_quote_confirm` |
| `2e + une autre` | skip NLU (regex + routeur) ou flags NLU | select + ask thème |
| `oui ajoute ceci` | skip NLU (regex `add_this`) | **append** + ask devis |

### Sélection d’activités & devis (`memory/quote_state.py`)

Source de vérité pour le PDF = slot `activites_selectionnees` (pas le texte du LLM).

| Message partenaire | Comportement Python |
|--------------------|---------------------|
| `le premier et le quatrième` / `1 et 4` | Indices → dernière présentation bot → **écrase** la sélection |
| `non c'est juste le premier et le quatrième` | Idem (correction) |
| `oui` / `c'est bon` | Confirme la sélection en cours ou la **dernière** présentation (max 4) |
| `ajoute ceci` / regex `add_this` | **Append** l’activité présentée à la sélection |
| `2e + une autre` / regex `wants_another` | Sélectionne l’indice, slot `awaiting_add_activity`, pas de devis |
| Indices sur **liste 2** si `awaiting_add_activity` | **Append** (ne remplace pas la liste 1) ; « juste 1 et 2 » remplace encore |
| Titres cités / `j'ai aimé ça` | Match titre catalogue |

Règles dures :
- Jamais confirmer tout `activites_discutees` d’une destination
- Cap devis : `CONFIRMATION_MAX_ACTIVITIES = 4` (PDF) ; la **liste affichée** peut aller jusqu’à 10 (`PRESENTATION_LIST_MAX`) pour mapper « 1 et 6 »
- `activites_proposees` = **dernière** présentation seulement (pas cumul)
- Indices : ignorer les messages LLM « activité sélectionnée / je prépare le devis » ; si indice > taille → fallback `proposees`
- « 1 » seul, « ajouter 6 aussi », « ajouter lactivite 6 » → sélection / append 0 token
- Le panneau frontend / `quote_ready` lit `compute_quote_state()` — si le PDF a N activités, c’est que N IDs sont en session
- `awaiting_quote_confirm` / `awaiting_add_activity` → `quote_ready=false` (pas de bouton PDF prématuré)

### Modules backend

| Module | Rôle |
|--------|------|
| `routes/` | Endpoints REST : `/chat`, `/activities`, `/orders`, `/quote`, `/partners` |
| `agent/orchestrator.py` | Chef d'orchestre — déterministe d'abord, sinon LLM + tools |
| `agent/intent_detector.py` | Intention : recherche, devis, commande, FAQ, support… |
| `agent/planner.py` | Prochaine action : question, recherche, présentation, devis |
| `agent/context_manager.py` | Sync léger des slots (profil, envies dont « mix de tout ») — complément LLM |
| `agent/nlu_extractor.py` | **NLU structuré** Claude → JSON intention / slots |
| `agent/destination_policy.py` | Hors catalogue **strict** (1–2 tokens) ; ignore si destination déjà active |
| `agent/support_policy.py` | Escalade **0 token** → e-mail support (`SUPPORT_EMAIL`) |
| `agent/partner_context.py` | White label : `partner_id` → nom agence, message d'accueil |
| `agent/response_generator.py` | Post-traitement réponse |
| `agent/llm_usage.py` | Suivi tokens par requête `/chat` |
| `search/catalog_search.py` | **Moteur catalogue** : requête → filtrage → scoring → Top K |
| `search/ranking.py` | Scoring activités — **soft profil** (boost, pas filtre dur) |
| `search/geo.py` | Pays, continents, `list_destinations`, alias |
| `search/themes.py` | Taxonomie thèmes B2B + détection mot entier (mer ≠ Merzouga) |
| `services/agent.py` | Re-export vers `orchestrator` |
| `services/data_loader.py` | Lecture CSV, cache |
| `tools/registry.py` | `search_catalog`, `list_destinations`, commandes, devis, escalade |
| `memory/` | Session + slots + historique |
| `memory/quote_state.py` | Sélection bornée, ordinaux (`premier`/`1 et 4`), `quote_ready`, parsing présentation |
| `prompts/` | `system_prompt.txt` (ton B2B), `nlu_extract.txt`, tunnel Antoine |
| `pdf/quote_generator.py` | Devis White Label PDF |
| `data/` | CSV catalogue |

### Modules supprimés (migration agentique ✅)

| Ancien module | Remplacé par |
|---------------|--------------|
| `catalog_context.py` | `search/catalog_search.py` |
| `destination_resolver.py` | `search/geo.py` + `catalog_search` |
| `slot_extractor.py` | `agent/context_manager.py` + `agent/nlu_extractor.py` |
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
- [x] `destinations.csv` — ~40 destinations (scrape B2B)
- [x] `faq.csv` — ~13 entrées (scrape B2B)
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
- Prod (plus tard) : `openai/gpt-4o`, `anthropic/claude-haiku-4-5`, etc. — **même code**, changer `LLM_MODEL` + clé API

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
- [x] Fallback LLM automatique Groq ↔ Gemini + retries (`llm_retry_max`, `llm_fallback_model`)
- [x] `memory/quote_state.py` — suivi activités proposées / sélectionnées pour le devis
- [x] **`nlu_extractor.py`** — NLU JSON structuré avant dialogue (`LLM_NLU_EXTRACT`)
- [x] **`support_policy.py`** — escalade e-mail 0 token
- [x] **`themes.py`** — taxonomie thèmes B2B + recherche région/thème
- [x] **`destination_policy.py`** — hors catalogue strict, garde-fous destination
- [x] Chemins 0 token dans orchestrator (continent, thème+région, tunnel, confirmation)
- [x] `agent/partner_context.py` — résolution agence White Label (`partner_id`, `nom_agence`)
- [x] `ChatResponse` enrichi : `quote_ready`, `quote_activities`, `destination`, `nom_agence`
- [x] Tests : `test_chat.py`, `test_tools.py`, `test_catalog_search.py`, `test_agent.py`, `test_conversation_scenarios.py`, `test_quote_state.py`, `test_zanzibar_search.py`

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

**Flux agent (actuel — juillet 2026)** :

1. `POST /chat` (+ `partner_id` optionnel → `sync_partner_from_id`)
2. `context_manager.sync_slots_from_message` — regex profil/envies/groupe (**0 token**)
3. **Chemins déterministes 0 token** (`orchestrator`) :
   - continent/pays → `geo.list_catalog_destinations_for_region`
   - thème + région → `themes` + `catalog_search.build_theme_region_reply`
   - retrait post-devis → `quote_revision`
   - **sélection / oui devis purs** → `is_pure_selection_or_confirm_message` + `quote_state`
   - support → `support_policy` (e-mail, pas conseiller chat)
   - qualification tunnel → ask destination / profil / envies (réponses templates)
   - hors catalogue → `destination_policy`
4. **NLU structuré** (`nlu_extractor`) si `LLM_NLU_EXTRACT=true` — langage flou / mixte → JSON
5. Re-passage 0 token si NLU détecte continent/pays/thème sans destination ville
6. **Python applique le JSON NLU** : `_try_activity_confirmation(nlu=…)` (select / append / ask thème / devis)
7. `intent_detector` (regex) + enrichissement `nlu.intent` → `planner.plan_next`
8. `catalog_search.search_from_context` + `ranking` (soft profil, thèmes mot entier)
9. **Dialogue LLM** seulement si étapes 3–8 n’ont pas déjà répondu :
   - system + mémoire + `NLU STRUCTURÉ` + JSON catalogue + tools natifs (Claude/GPT)
10. `response_generator.sanitize_response` + `record_discussed_activities_from_text`
11. Retour `ChatResponse` (`quote_ready`, `quote_url`, `llm_used`, tokens)

**Deux appels Claude possibles par message** : (1) NLU extract ~150–400 tokens, (2) dialogue ~500–3000 tokens. Beaucoup de messages = **0 token** (badge « Réponse catalogue »).

**Limitations connues (gratuit)** :
- Groq / Gemini free tier : erreurs 429 (quota saturé) → fallback auto vers l'autre fournisseur si clé présente, sinon message « service saturé »
- Solution : attendre, configurer les deux clés (Groq + Gemini), ou passer à une API payante (GPT-4, Claude)

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
  - `partner_id`, `nom_agence` (body `POST /chat`, URL `?partner_id=`, ou tool)
  - `devis_ref`, `validite_jours` (7 j par défaut via `generate_quote`)
- [x] `memory/quote_state.py` — activités proposées, sélection conversationnelle, `quote_ready`
- [x] Ne pas redemander une info déjà connue (prompts + `planner.py` + tests)
- [x] Validation destination catalogue (`geo.resolve_destination_name`, rejet faux lieux)
- [ ] Short / Long / Session memory distinctes — structure prête, short seule en MVP
- [x] Extraction slots avancée via LLM — `nlu_extractor.py` (NLU JSON, `LLM_NLU_EXTRACT`)
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
- [x] `routes/quote.py` → POST `/quote`, POST `/quote/from-session`, GET `/quotes/{filename}`, GET `/session/{id}/quote-state`
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
- [x] Page HTML/CSS/JS (`frontend/`) — thème sombre, layout chat + panneau devis
- [x] Widget chat : zone messages, input
- [x] Appels API vers `POST /chat`
- [x] Gestion `session_id` + `partner_id` (localStorage + `?partner_id=` URL)
- [x] Frontend servi par FastAPI sur `http://127.0.0.1:8000/` (pas besoin de Live Server)
- [x] Messages d'erreur API affichés dans le chat
- [x] Panneau devis : résumé activités sélectionnées, état `quote_ready`, hint contextuel
- [x] Mise à jour panneau depuis `ChatResponse` + `GET /session/{id}/quote-state` au chargement
- [x] Accueil personnalisé agence via `GET /partners/{partner_id}` (`greeting_message`)
- [x] Bouton **Générer le devis PDF** — `POST /quote/from-session`, sans appel LLM
- [x] Téléchargement PDF inline (`quote_url` chat ou bouton panneau)
- [x] Anti-simulation : filtre réponses « devis simulé / e-mail » + activités ancrées JSON
- [x] Landing + widget chat flottant style Day Experience (popup)
- [x] Dock dev : badge tokens LLM (`llm_used`, tokens) + panneau devis QA
- [ ] Affichage des activités recommandées dans le chat (cards structurées, pas seulement texte)
- [ ] Design responsive (`@media`), charte graphique Day Experience officielle

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
- [x] Thèmes sans destination : mer/plage, montagne, Sahara via `themes.py` + `catalog_search` (région + thème)
- [x] Anti-hallucination : pas d'activités/devis sans JSON catalogue (`context_has_activities`)
- [x] Tests scénarios : Maroc, Sahara, Paris, Tour Eiffel, groupe 20, Marrakech couple, plage (`test_conversation_scenarios.py`)

---

### Étape 9 — Escalade conseiller humain ✅ (MVP)

**Tâches** :
- [x] Règles d'escalade détaillées dans system prompt (remboursement, litige, hors catalogue, insatisfaction…)
- [x] Tool `escalate_to_advisor` + flag session
- [x] **`support_policy.py`** — réponse **0 token** orientant vers e-mail (`SUPPORT_EMAIL`), pas de « conseiller dans le chat »
- [x] Produit hors catalogue → message explicite + suggestion escalade (ex. Corse Saleccia)
- [x] Tests `test_support_escalation.py`
- [ ] Log des escalades (fichier ou table) — reporté phase 2

---

### Étape 10 — Tests et qualité ✅ (MVP)

**Tests fonctionnels** :
- [x] Recherche activités par critères (Paris, Maroc, Sahara, profil famille)
- [x] Anti-hallucination : Tour Eiffel, Corse, prix catalogue, plage sans destination
- [x] Mémoire : destination, exclusions, taille groupe, Marrakech 5j couple
- [x] Tunnel : `test_agent.py`, `test_context_manager.py`, planner
- [ ] Conversation fluide multi-tours E2E automatisée — manuel OK
- [x] Génération PDF complète — étape 6 (`test_quote.py`, `test_quote_state.py`)
- [x] Escalade support e-mail — `test_support_escalation.py`
- [x] Architecture NLU, thèmes, sélection, geo — `test_nlu_extractor`, `test_theme_search`, `test_selection_guards`, `test_destination_policy`, `test_geo_country`

**Tests techniques** :
- [x] pytest — **138+ tests** (architecture NLU, thèmes, sélection, support, geo…)
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

Version API : **0.3.0** (`backend/main.py`)

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/` | Page de démo frontend (HTML) |
| POST | `/chat` | Message agent — retourne `reply`, `quote_ready`, `quote_activities`, `quote_url`… |
| GET | `/activities` | Liste/filtre activités (`destination`, `budget`, `profil`, `q`) |
| GET | `/activities/{id}` | Détail activité |
| GET | `/destinations` | Liste destinations catalogue |
| GET | `/partners/{partner_id}` | Infos partenaire + `greeting_message` White Label |
| GET | `/session/{session_id}/quote-state` | État devis session (activités, `quote_ready`, champs manquants) |
| POST | `/quote` | Générer devis PDF (IDs activités explicites) |
| POST | `/quote/from-session` | Générer devis depuis la session (sans LLM) |
| GET | `/quotes/{filename}` | Télécharger un PDF généré |
| GET | `/orders/{reference}` | Statut commande |
| GET | `/health` | Health check |
| GET | `/docs` | Documentation Swagger |

---

## Variables d'environnement

Fichier `.env` à la **racine du projet** (lu par `backend/app/config.py`).

```env
# --- LLM (un seul actif via LLM_MODEL) ---
GROQ_API_KEY=
GEMINI_API_KEY=
ANTHROPIC_API_KEY=
# OPENAI_API_KEY=

# Gratuit / dev
# LLM_MODEL=groq/llama-3.3-70b-versatile
# LLM_MODEL=gemini/gemini-2.0-flash

# Payant — recommandé démo / prod
LLM_MODEL=anthropic/claude-haiku-4-5
# LLM_MODEL=anthropic/claude-sonnet-4-5
# LLM_MODEL=openai/gpt-4o-mini

LLM_FALLBACK_MODEL=
# LLM_FALLBACK_MODEL=anthropic/claude-haiku-4-5

# Optimisation tokens
LLM_MAX_TOKENS=512
LLM_TIMEOUT=90
LLM_RETRY_MAX=1
LLM_RETRY_DELAY=2.0
LLM_HISTORY_LIMIT=8
LLM_CATALOG_INJECT_LIMIT=4
LLM_COMPACT_PROMPT=true
LLM_LOG_USAGE=true
LLM_NLU_EXTRACT=true

# --- Support (escalade e-mail) ---
SUPPORT_EMAIL=support@day-experience-demo.com

# --- API ---
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=true
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:5500,http://localhost:8000

# --- Scrape B2B ---
B2B_LOGIN=
B2B_PASSWORD=
B2B_AGENT=1268|Mme Day Exeprience
B2B_REQUEST_DELAY=0.6
B2B_MAX_RETRIES=5
```

**Changer de fournisseur LLM** : modifier `LLM_MODEL` + la clé correspondante, redémarrer uvicorn.  
Claude (payant) : `ANTHROPIC_API_KEY` + `LLM_MODEL=anthropic/claude-haiku-4-5`.  
Optimisation tokens : `LLM_MAX_TOKENS=512`, `LLM_HISTORY_LIMIT=8`, `LLM_CATALOG_INJECT_LIMIT=4`, `LLM_COMPACT_PROMPT=true` (tunnel injecté seulement en qualification).  
Les réponses déterministes Python (hors catalogue, pays, confirmation) = **0 token**.  
Si Groq **et** Gemini sont configurés, l'orchestrateur bascule automatiquement en cas de quota (429).  
L'architecture (orchestrator, catalog_search, tools, mémoire, quote_state) reste identique.

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
7. Frontend chat                     🔄 partiel (chat + panneau devis OK, cards chat à faire)
8. Tunnel Antoine (planner)          ✅ MVP
9. Escalade + edge cases             ✅ MVP
10. Tests pytest                     ✅ MVP (138+ tests)
11. Déploiement démo                 ⬜
12. Architecture NLU + garde-fous    ✅ (NLU JSON, 0 token, thèmes, soft profil, ordinaux, support e-mail)
```

### Migration architecture agentique (Sprints 1–4) ✅

| Sprint | Contenu | Statut |
|--------|---------|--------|
| 1 | Supprimer `catalog_context`, `destination_resolver`, `slot_extractor`, `tunnel_guidance` | ✅ |
| 2 | Créer `intent_detector`, `planner`, `catalog_search`, `ranking` | ✅ |
| 3 | Fusionner tools → `search_catalog()` | ✅ |
| 4 | Créer `response_generator` | ✅ |
| 12 | NLU JSON, chemins 0 token, thèmes, sélection, support e-mail | ✅ |
| 5 | PostgreSQL derrière `catalog_search` | ⬜ |
| 6 | API Day Experience | ⬜ |
| 7 | RAG / Vector DB | ⬜ |

**Prochaine étape suggérée** : **Étape 7 — Frontend cards** (activités structurées dans le chat) ou **Étape 11 — Déploiement démo**.

---

## Notes pour les sessions Claude / Cursor

Lors de chaque session de dev, indiquer :
1. **Étape en cours** (ex. « Étape 7 — Frontend cards »)
2. **Tâches cochées / restantes** dans ce fichier
3. **Blocages** (données manquantes, quota LLM, template PDF…)

Mettre à jour les `[ ]` → `[x]` dans ce fichier au fur et à mesure.

### État au 16/07/2026

- **Architecture** : **`intent_router`** (matrice fermée) → 0 token → NLU (flou) → Python → dialogue LLM
- **Principe** : Claude comprend le langage ; Python = vérité catalogue, sélection, devis, escalade
- **Machine à états** : `agent/conversation_state.py` — `ConvState` unique dérivé des slots (`derive_state`), priorité `quote_confirm > city_confirm > city_pick > add_activity > post_quote > presenting > qualifying` ; `allows_destination_change` interdit tout changement de lieu pendant ask devis / ajout
- **Lieu inconnu = whitelist** : `detect_unknown_place_request` exige (1) état autorisant un changement de destination, (2) `matches_known_intent` = False (confirmations, sélection, budget, thèmes, pays, support consolidés), (3) toponyme isolé 1–2 tokens ; `activate_unavailable_destination` **non destructif** si destination catalogue + sélection en cours
- **Classifieur unique** : `conversation_state.classify_intent(text) → Intent` (enum fermé : greeting, support, confirm, select_indices, add_this, select_and_add, other_options, wants_another, reject_remove, qualification, country_region, budget_or_search, theme, unknown) — priorité encodée à UN endroit ; `matches_known_intent` et `should_run_nlu` le consomment
- **NLU sur l'ambigu** : `should_run_nlu` = skip si intent déterministe / FAQ / lieu hors catalogue isolé, sinon **NLU** (typos, phrases mixtes, questions factuelles) ; le NLU reçoit `etat_conversation` (machine à états) dans la mémoire injectée — `nlu_extract.txt` documente l'interprétation par état
- **Normalisation entrée** : `normalize_message` (NFC, apostrophes droites, espaces) appliqué une fois en tête de `_chat` — les regex ne gèrent plus les variantes unicode
- **Anti whack-a-mole** : scénarios dans `test_scenario_router.py` ; nouveau cas = nouveau test, pas un patch isolé
- **Tests golden** : `test_golden_transcripts.py` rejoue mot pour mot les transcripts réels qui ont cassé (Afrique du Sud : j'ai pas aimé / autre option / typos pays ; Tokyo : les 3 premiers → ouii → devis 3 activités) avec `litellm.completion` mocké → **0 token garanti** sur toute la conversation
- **Traçabilité routage** : chaque message logue `chat.in session=… state=… route=kind/reason intent=… msg=…` puis `chat.out tools=… llm=…|0-token tokens=…` (INFO, visible console uvicorn) — diagnostic misroute sans debugger
- **NLU** : skip saluts / pays / sélection / append / autre activité regex / routes 0 token ; utilisé pour langage flou restant
- **Budget** : extraction `200 euro` ; « augmentez budget » ≠ lieu ; Afrique sous plafond → fallback moins chères
- **QA** : bouton **Nouveau** (widget) + `DELETE /session/{id}`
- **FAQ widget** : onglet Chat / FAQ + `GET /faq`
- **FAQ chat** : `agent/faq_policy.py` — question métier (commission, réservation, annulation…) → meilleure entrée `faq.csv`, 0 token (`faq_lookup`)
- **City confirm** : `agent/destination_confirm.py` — slots `awaiting_city_confirm` / `awaiting_city_pick` ; « oui » après offre 1 ville → destination + search (plus de re-ask)- **Thèmes** : `search/themes.py` — plage, montagne, sahara, gastronomie… ; recherche région + thème
- **Profil** : soft boost dans `ranking` (plus de filtre dur)
- **Sélection** : ordinaux, append multi-listes (`awaiting_add` → indices liste 2 **ajoutent**), « 1 et 6 », « ajouter 6 », « les 3 premiers » = exactement 3 IDs ; cap 4 = plafond devis seulement (ne remplit pas jusqu’à 4)
- **Confirm devis** : `oui` / `ouii` / `ouais` / `le devis` ; pendant `awaiting_quote_confirm` → jamais traité comme un lieu hors catalogue
- **Refus liste** : « j'ai pas aimé » / « autre option » → nouvelle liste (exclut déjà proposées), **pas** « sélection vide » ni ask thème add
- **Afrique du Sud** : typos `afrique de sud` / `sude` → pays (Parc Kruger), **pas** continent Afrique (Le Caire…)
- **Support** : `support_policy` — e-mail déterministe, 0 token
- Tools : `search_catalog`, `list_destinations`, détails, commandes, devis, escalade
- **Devis** : IDs session seulement (`activites_selectionnees`) ; pas de re-fill auto à 4 au « oui » ; `awaiting_quote_confirm` / `awaiting_add_activity`
- Suivi usage LLM : logs + badge frontend (`llm_used`, tokens)
- Ton B2B dans `system_prompt.txt` (pas d’emoji, messages courts)
- White label : `partner_id` → agence + accueil
- Frontend : popup chat + badge tokens + bouton **Nouveau** — `http://127.0.0.1:8000/?partner_id=1`
- **226 tests** pytest (+ scénarios routeur + transcripts golden)
- LLM recommandé : `anthropic/claude-haiku-4-5` (`LLM_MODEL` + `ANTHROPIC_API_KEY`) ; `LLM_NLU_EXTRACT=true`
- **Diff vs ancien flux** : routeur d’abord ; pas de regex infinie pour le langage métier
- `policies.csv` : en-têtes seuls (données annulation non disponibles côté B2B)
- Prochaine évolution catalogue : SQL → API Day Experience → RAG (sans refonte agent)
