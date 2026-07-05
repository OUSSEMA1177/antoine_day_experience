#!/usr/bin/env python3
"""
Extrait les partenaires (colonne PARTNER) depuis data day experiencee.csv
et génère backend/data/partners.csv
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GLOBAL_CSV = DATA_DIR / "data day experiencee.csv"
OUTPUT = DATA_DIR / "partners.csv"

LEGAL_SUFFIXES = (
    ", with Tax Number",
    " with Tax Number",
    ", with Travel License",
    " with Travel License",
)


def clean_name(raw: str) -> str:
    name = raw.strip()
    for sep in LEGAL_SUFFIXES:
        if sep in name:
            name = name.split(sep)[0]
    return name.strip().rstrip(",")


def extract_email(raw: str) -> str:
    match = re.search(r"[\w.+-]+@[\w.-]+\.\w+", raw)
    return match.group(0) if match else ""


def extract_contact(raw: str) -> str:
    parts = []
    tax = re.search(r"Tax Number\s+([^,]+?)(?:\s+and\s+Travel|\s*,|$)", raw, re.I)
    if tax:
        parts.append(f"Tax: {tax.group(1).strip()}")
    license_ = re.search(r"Travel License Number\s+([^,]+)", raw, re.I)
    if license_:
        parts.append(f"License: {license_.group(1).strip()}")
    return " | ".join(parts)


def main() -> None:
    if not GLOBAL_CSV.exists():
        raise SystemExit(f"Fichier introuvable : {GLOBAL_CSV}")

    aggregated: dict[str, dict] = defaultdict(
        lambda: {"currency": "", "countries": set(), "count": 0, "raw": ""}
    )

    with GLOBAL_CSV.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw = (row.get("PARTNER") or "").strip()
            if not raw:
                continue
            entry = aggregated[raw]
            entry["raw"] = raw
            entry["count"] += 1
            entry["currency"] = (row.get("PARTNERCURRENCY") or entry["currency"]).strip()
            country = (row.get("DESTINATIONCOUNTRY") or "").strip()
            if country:
                entry["countries"].add(country)

    rows: list[dict] = []
    for i, (raw, info) in enumerate(
        sorted(aggregated.items(), key=lambda x: (-x[1]["count"], x[0].lower())),
        start=1,
    ):
        email = extract_email(raw)
        nom = clean_name(raw)
        if email and nom == email:
            nom = email.split("@")[0].replace("+", " ").replace(".", " ").title()

        countries = sorted(info["countries"])
        pays = countries[0] if len(countries) == 1 else (countries[0] if countries else "")

        rows.append(
            {
                "id": i,
                "nom_agence": nom,
                "email": email,
                "logo_url": "",
                "contact": extract_contact(raw),
                "ville": "",
                "pays": pays,
                "partner_currency": info["currency"],
                "offres_count": info["count"],
                "nom_complet": raw,
            }
        )

    fieldnames = [
        "id",
        "nom_agence",
        "email",
        "logo_url",
        "contact",
        "ville",
        "pays",
        "partner_currency",
        "offres_count",
        "nom_complet",
    ]

    with OUTPUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Written {len(rows)} partners -> {OUTPUT}")


if __name__ == "__main__":
    main()
