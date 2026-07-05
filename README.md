# Day Experience AI — Agent conversationnel B2B

Prototype MVP d'un agent IA conversationnel pour accompagner les partenaires B2B de Day Experience (recherche d'activités, tunnel Antoine, devis White Label PDF).

## Structure

```
antoine/
├── frontend/          # Interface Web (chat widget)
├── backend/
│   ├── app/
│   ├── routes/        # API FastAPI
│   ├── services/      # Logique métier
│   ├── tools/         # Outils de l'agent (tool calling)
│   ├── memory/        # Mémoire conversationnelle
│   ├── prompts/       # System prompts
│   ├── pdf/           # Génération devis PDF
│   ├── data/          # Fichiers CSV (MVP)
│   └── main.py        # Point d'entrée FastAPI
├── claud.md           # Roadmap et tâches de développement
└── README.md
```

## Démarrage rapide

### 1. Collecte des données B2B

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
# Copier ../.env.example → ../.env (B2B_LOGIN, B2B_PASSWORD)
python scripts/scrape_b2b.py --destinations 2222,4362
```

### 2. Lancer l'API

```bash
uvicorn main:app --reload
```

Endpoints disponibles :
- `GET /health` — statut serveur
- `GET /activities?destination=Paris&budget=50&profil=couple` — recherche activités
- `GET /activities/{id}` — détail activité
- `GET /destinations` — liste destinations
- `GET /orders/{reference}` — statut commande
- `POST /chat` — agent conversationnel `{ "session_id", "message" }`
- `GET /docs` — documentation Swagger

## Stack MVP

- **Backend** : FastAPI, LiteLLM (Groq Llama-3-70b ou Gemini Flash)
- **Données** : CSV (migration future vers BDD / API)
- **Frontend** : page Web de démonstration avec widget chat
