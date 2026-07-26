#!/usr/bin/env python3
"""
Collecte les données catalogue depuis la plateforme B2B Day Experience.

Prérequis :
  - Compte agence autorisé (identifiants dans .env)
  - pip install -r requirements.txt

Usage :
  cd backend
  python scripts/scrape_b2b.py
  python scripts/scrape_b2b.py --destinations 2222,4362
  python scripts/scrape_b2b.py --max-destinations 5 --skip-details
  python scripts/scrape_b2b.py --full
  python scripts/scrape_b2b.py --full --resume   # reprend après coupure réseau
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
CHECKPOINT_EVERY = 25

sys.path.insert(0, str(SCRIPT_DIR))

from b2b_client import ActivityCard, ActivityDetail, B2BClient, B2BConfig  # noqa: E402

load_dotenv(BACKEND_DIR.parent / ".env")
load_dotenv(BACKEND_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("scrape_b2b")

ACTIVITY_FIELDS = [
    "id",
    "destination_id",
    "titre",
    "description",
    "prix",
    "prix_public",
    "duree",
    "langues",
    "inclusions",
    "categorie",
    "profil_cible",
    "horaires",
    "conditions_annulation",
]


def checkpoint_dir(output_dir: Path) -> Path:
    return output_dir / ".scrape_checkpoint"


def save_checkpoint(
    cp_dir: Path,
    destinations: dict[int, str],
    cards: list[ActivityCard],
    details: dict[str, ActivityDetail],
) -> None:
    cp_dir.mkdir(parents=True, exist_ok=True)
    (cp_dir / "destinations.json").write_text(
        json.dumps({str(k): v for k, v in destinations.items()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (cp_dir / "cards.json").write_text(
        json.dumps([asdict(c) for c in cards], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (cp_dir / "details.json").write_text(
        json.dumps({k: asdict(v) for k, v in details.items()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_checkpoint(cp_dir: Path) -> tuple[dict[int, str], list[ActivityCard], dict[str, ActivityDetail]] | None:
    cards_path = cp_dir / "cards.json"
    if not cards_path.exists():
        return None
    destinations = {
        int(k): v for k, v in json.loads((cp_dir / "destinations.json").read_text(encoding="utf-8")).items()
    }
    cards = [ActivityCard(**row) for row in json.loads(cards_path.read_text(encoding="utf-8"))]
    details_raw = json.loads((cp_dir / "details.json").read_text(encoding="utf-8")) if (cp_dir / "details.json").exists() else {}
    details = {k: ActivityDetail(**v) for k, v in details_raw.items()}
    return destinations, cards, details


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    logger.info("Écrit %s (%s lignes)", path.name, len(rows))


def build_destinations_rows(destinations: dict[int, str]) -> list[dict]:
    return [
        {
            "id": vid,
            "nom": name,
            "pays": "",
            "region": "",
            "aliases": "",
            "description": f"Activités touristiques à {name}",
            "saison_ideale": "",
        }
        for vid, name in sorted(destinations.items(), key=lambda x: x[1].lower())
    ]


def build_activities_rows(
    cards: list[ActivityCard],
    details: dict[str, ActivityDetail],
    client: B2BClient,
) -> list[dict]:
    rows: list[dict] = []
    for card in cards:
        detail = details.get(card.id)
        titre = card.titre
        description = ""
        prix_net = ""
        inclusions = ""
        annulation = ""
        categorie = ""
        duree = card.duree
        langues = card.langues
        profil = client.infer_profil(card.titre, "")

        if detail:
            titre = detail.titre or titre
            description = detail.description
            prix_net = detail.prix_net or prix_net
            inclusions = detail.inclusions
            annulation = detail.conditions_annulation
            categorie = detail.categorie
            duree = detail.duree or duree
            langues = detail.langues or langues
            profil = client.infer_profil(titre, categorie)

        rows.append(
            {
                "id": card.id,
                "destination_id": card.destination_id,
                "titre": titre,
                "description": description,
                "prix": prix_net or card.prix_public,
                "prix_public": card.prix_public,
                "duree": duree,
                "langues": langues,
                "inclusions": inclusions,
                "categorie": categorie,
                "profil_cible": profil,
                "horaires": "",
                "conditions_annulation": annulation,
            }
        )
    return rows


def write_all_csvs(
    out: Path,
    destinations: dict[int, str],
    cards_list: list[ActivityCard],
    details: dict[str, ActivityDetail],
    client: B2BClient,
    agent: str,
) -> None:
    dest_rows = build_destinations_rows(destinations)
    act_rows = build_activities_rows(cards_list, details, client)
    faq_rows = [{"id": i, **row} for i, row in enumerate(client.fetch_faq(), start=1)]
    order_rows = normalize_orders(client.fetch_orders())
    policy_rows = build_policies_rows(act_rows)
    partner_rows = [
        {
            "id": 1,
            "nom_agence": "Day Experience Demo",
            "email": "demo@day-experience.com",
            "logo_url": "",
            "contact": agent.split("|")[-1] if "|" in agent else agent,
            "ville": "",
            "pays": "France",
        }
    ]

    write_csv(out / "destinations.csv", ["id", "nom", "pays", "region", "aliases", "description", "saison_ideale"], dest_rows)
    write_csv(out / "activities.csv", ACTIVITY_FIELDS, act_rows)
    write_csv(out / "faq.csv", ["id", "question", "reponse", "categorie"], faq_rows)
    write_csv(out / "orders.csv", ["id", "reference", "partner_id", "statut", "date", "activites", "montant"], order_rows)
    write_csv(
        out / "policies.csv",
        ["id", "activite_id", "conditions_annulation", "delai_remboursement", "politique_commerciale"],
        policy_rows,
    )
    write_csv(
        out / "partners.csv",
        ["id", "nom_agence", "email", "logo_url", "contact", "ville", "pays"],
        partner_rows,
    )


def write_activities_only(
    out: Path,
    cards_list: list[ActivityCard],
    details: dict[str, ActivityDetail],
    client: B2BClient,
) -> None:
    """Sauvegarde intermédiaire des activités (sans relancer FAQ/orders)."""
    act_rows = build_activities_rows(cards_list, details, client)
    write_csv(out / "activities.csv", ACTIVITY_FIELDS, act_rows)


def build_policies_rows(activities: list[dict]) -> list[dict]:
    rows = []
    for i, act in enumerate(activities, start=1):
        if not act.get("conditions_annulation"):
            continue
        rows.append(
            {
                "id": i,
                "activite_id": act["id"],
                "conditions_annulation": act["conditions_annulation"],
                "delai_remboursement": "",
                "politique_commerciale": "",
            }
        )
    return rows


def normalize_orders(raw_orders: list[dict]) -> list[dict]:
    if not raw_orders:
        return [
            {
                "id": 1,
                "reference": "DEMO-001",
                "partner_id": 1,
                "statut": "confirmée",
                "date": "",
                "activites": "",
                "montant": "",
            }
        ]

    rows = []
    for i, order in enumerate(raw_orders, start=1):
        rows.append(
            {
                "id": i,
                "reference": order.get("référence") or order.get("reference") or order.get("dossier") or f"ORD-{i}",
                "partner_id": 1,
                "statut": order.get("statut") or order.get("état") or order.get("etat") or "",
                "date": order.get("date") or "",
                "activites": order.get("activité") or order.get("activite") or order.get("prestation") or "",
                "montant": order.get("montant") or order.get("total") or "",
            }
        )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collecte CSV depuis b2b.day-experience.com")
    parser.add_argument(
        "--destinations",
        type=str,
        default="",
        help="IDs villes séparés par des virgules (ex: 2222,4362). Vide = auto-découverte.",
    )
    parser.add_argument(
        "--max-destinations",
        type=int,
        default=0,
        help="Limite le nombre de destinations (0 = toutes découvertes).",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="Pages max par destination (0 = toutes).",
    )
    parser.add_argument(
        "--skip-details",
        action="store_true",
        help="Ne pas ouvrir chaque fiche produit (plus rapide, moins de champs).",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Collecte complète : toutes destinations, toutes pages, détails produits.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=float(os.getenv("B2B_REQUEST_DELAY", "0.35")),
        help="Délai entre requêtes (secondes).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DATA_DIR,
        help="Dossier de sortie CSV.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reprendre depuis .scrape_checkpoint/ (liste + détails déjà collectés).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=int(os.getenv("B2B_MAX_RETRIES", "5")),
        help="Nombre de tentatives par requête HTTP en cas d'erreur réseau.",
    )
    return parser.parse_args()


def fetch_details_with_checkpoint(
    client: B2BClient,
    cards_list: list[ActivityCard],
    details: dict[str, ActivityDetail],
    out: Path,
    cp: Path,
    destinations: dict[int, str],
) -> dict[str, ActivityDetail]:
    pending = [c for c in cards_list if c.id not in details]
    logger.info(
        "Fiches produit : %s déjà collectées, %s restantes",
        len(details),
        len(pending),
    )

    for i, card in enumerate(pending, start=1):
        idx = len(details) + 1
        logger.info("Détail produit %s/%s — %s", idx, len(cards_list), card.id)
        try:
            details[card.id] = client.fetch_activity_detail(card.id)
        except Exception as exc:
            logger.error("Échec fiche %s après retries : %s — ignorée", card.id, exc)
            continue

        if i % CHECKPOINT_EVERY == 0:
            save_checkpoint(cp, destinations, cards_list, details)
            write_activities_only(out, cards_list, details, client)
            logger.info("Checkpoint sauvegardé (%s détails)", len(details))

    return details


def main() -> int:
    args = parse_args()

    login = os.getenv("B2B_LOGIN", "")
    password = os.getenv("B2B_PASSWORD", "")
    agent = os.getenv("B2B_AGENT", "1268|Mme Day Exeprience")

    if not login or not password:
        logger.error(
            "Identifiants manquants. Copiez .env.example vers .env et renseignez B2B_LOGIN / B2B_PASSWORD."
        )
        return 1

    if args.full:
        args.skip_details = False
        args.max_destinations = 0
        args.max_pages = 0
        if args.delay <= 0.35:
            args.delay = 0.6

    out = args.output_dir
    cp = checkpoint_dir(out)

    config = B2BConfig(
        login=login,
        password=password,
        agent_value=agent,
        request_delay=args.delay,
        max_retries=args.max_retries,
    )
    client = B2BClient(config)

    loaded = load_checkpoint(cp) if args.resume else None
    if loaded:
        destinations, cards_list, details = loaded
        logger.info(
            "Reprise checkpoint : %s destinations, %s activités, %s détails",
            len(destinations),
            len(cards_list),
            len(details),
        )
    else:
        destinations = {}
        if args.destinations.strip():
            for part in args.destinations.split(","):
                part = part.strip()
                if not part:
                    continue
                vid = int(part)
                destinations[vid] = client.resolve_destination_name(vid)
        else:
            logger.info("Découverte des destinations…")
            destinations = client.discover_destinations()
            for vid, name in list(destinations.items()):
                if name.startswith("Ville-"):
                    destinations[vid] = client.resolve_destination_name(vid)

        if args.max_destinations > 0:
            destinations = dict(list(destinations.items())[: args.max_destinations])

        if not destinations:
            logger.error("Aucune destination trouvée.")
            return 1

        logger.info("Destinations à collecter : %s", len(destinations))

        all_cards: list[ActivityCard] = []
        max_pages = args.max_pages or None
        for vid, name in sorted(destinations.items(), key=lambda x: x[1].lower()):
            logger.info("Collecte activités — %s (%s)", name, vid)
            cards = client.fetch_activities_for_destination(vid, name, max_pages=max_pages)
            logger.info("  → %s activités pour %s", len(cards), name)
            all_cards.extend(cards)

        unique_cards = {c.id: c for c in all_cards}
        cards_list = list(unique_cards.values())
        logger.info("Total activités uniques : %s", len(cards_list))

        details = {}
        save_checkpoint(cp, destinations, cards_list, details)
        write_csv(out / "destinations.csv", ["id", "nom", "pays", "region", "aliases", "description", "saison_ideale"], build_destinations_rows(destinations))
        write_activities_only(out, cards_list, details, client)
        logger.info("Liste activités sauvegardée (sans détails produit).")

    if not args.skip_details:
        details = fetch_details_with_checkpoint(client, cards_list, details, out, cp, destinations)
        save_checkpoint(cp, destinations, cards_list, details)

    write_all_csvs(out, destinations, cards_list, details, client, agent)
    logger.info("Collecte terminée → %s", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
