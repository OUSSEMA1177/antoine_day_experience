# Day Experience AI — Agent conversationnel B2B

Agent IA pour les **partenaires B2B** de Day Experience (agences, tour-opérateurs) : qualification du besoin, recherche catalogue, sélection d’activités, devis White Label PDF.

**Principe** : Claude comprend le langage ; Python garantit le catalogue, la sélection et le devis.

## Fonctionnalités MVP

- Tunnel conversationnel « Antoine » (destination → profil → envies → activités → devis)
- Chemins **0 token** pour pays / continent, thèmes, sélection, confirmation devis, FAQ, support
- NLU (LLM → JSON) uniquement sur le langage flou / mixte
- Machine à états (`qualifying`, `presenting_list`, `awaiting_quote_confirm`, …)
- Listes d’activités avec **liens vers les fiches B2B** (`produit.cfm?idActivity=…`)
- Devis PDF White Label (max 4 activités, IDs session uniquement)
- Widget chat démo + badge tokens LLM + bouton Nouveau
- Messages catalogue sans markdown `**` (ton B2B)

## Architecture

```
Message partenaire
        │
        ▼
 normalize_message + intent_router (matrice fermée)
        │
        ├─ 0 token (pays, thème, sélection, devis, FAQ, support…)
        │
        ├─ NLU (flou) → Python (catalogue / devis)
        │
        └─ Dialogue LLM (dernier recours)
```

Modules clés côté backend :

| Module | Rôle |
|--------|------|
| `agent/orchestrator.py` | Dispatch + logs `chat.in` / `chat.out` |
| `agent/conversation_state.py` | États + `classify_intent` |
| `agent/intent_router.py` | Route déterministe |
| `agent/nlu_extractor.py` | Extraction JSON (Claude) |
| `memory/quote_state.py` | Sélection / confirmation devis |
| `search/` | Catalogue, geo, thèmes, ranking |

Guide de développement détaillé : [`claud.md`](claud.md)

## Structure

```
antoine/
├── frontend/              # Widget chat (HTML/CSS/JS)
├── backend/
│   ├── agent/             # Orchestrateur, NLU, états, policies
│   ├── memory/            # Sessions + quote state
│   ├── search/            # Catalogue / geo / thèmes
│   ├── routes/            # FastAPI (/chat, /faq, …)
│   ├── tools/             # Tool calling
│   ├── pdf/               # Génération devis
│   ├── data/              # CSV MVP
│   ├── prompts/           # system + nlu_extract
│   ├── tests/             # ~226 tests (dont golden transcripts)
│   └── main.py
├── .env.example
├── claud.md
└── README.md
```

## Démarrage rapide

### 1. Environnement

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
```

Copier `.env.example` → `.env` à la racine du repo, puis renseigner au minimum :

```env
ANTHROPIC_API_KEY=...
LLM_MODEL=anthropic/claude-haiku-4-5
LLM_NLU_EXTRACT=true
SUPPORT_EMAIL=support@example.com
```

Autres modèles possibles : Groq, Gemini, OpenAI (voir `.env.example`).

### 2. Lancer l’API

```bash
cd backend
uvicorn main:app --reload
```

Ouvrir : [http://127.0.0.1:8000/?partner_id=1](http://127.0.0.1:8000/?partner_id=1)

### 3. Endpoints utiles

| Méthode | Chemin | Description |
|---------|--------|-------------|
| `GET` | `/health` | Santé serveur |
| `POST` | `/chat` | Agent `{ "session_id", "message", "partner_id?" }` |
| `DELETE` | `/session/{id}` | Reset session (bouton Nouveau) |
| `GET` | `/faq` | FAQ partenaire |
| `GET` | `/activities` | Recherche activités |
| `GET` | `/destinations` | Destinations catalogue |
| `GET` | `/orders/{reference}` | Statut commande |
| `GET` | `/docs` | Swagger |

### 4. Tests

```bash
cd backend
pytest -q
```

Inclut des **transcripts golden** (Tokyo, Afrique du Sud) qui verrouillent les bugs de routage corrigés.

### 5. (Optionnel) Scrape catalogue B2B

```bash
# Dans .env : B2B_LOGIN, B2B_PASSWORD
python scripts/scrape_b2b.py --destinations 2222,4362
```

## Hébergement (sans Docker)

Pour un serveur / VPS :

1. Cloner le repo et créer `.env` à la racine (copier `.env.example`)
2. Installer les deps (`cd backend && python -m venv .venv && pip install -r requirements.txt`)
3. Lancer **sans** `--reload` :

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

4. Ouvrir `http://<hôte>:8000/?partner_id=1`

**Limitations MVP** : sessions en mémoire (perdues au redémarrage), pas d’auth API, pas de sync panier B2B.

## Stack

- **Backend** : FastAPI, LiteLLM
- **LLM recommandé** : `anthropic/claude-haiku-4-5`
- **Données** : CSV (évolution prévue SQL / API Day Experience)
- **Frontend** : page de démo + widget chat

## Exemples de parcours 0 token

- « Afrique du Sud » → Parc Kruger (typos `afrique de sude` gérées)
- « les 3 premiers » puis « ouii » → devis avec **exactement 3** activités
- « j’ai pas aimé » / « autre option » → nouvelle liste, pas demande de thème add
- Questions métier (commission, annulation…) → FAQ CSV

## Licence / contexte

Prototype MVP Stage — usage interne Day Experience / démo partenaires.
