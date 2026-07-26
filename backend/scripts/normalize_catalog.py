#!/usr/bin/env python3
"""Normalise destinations.csv et fusionne les activités orphelines."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.catalog_normalization import (
    DESTINATION_CANONICAL,
    DESTINATION_FIELDS,
    DESTINATION_MERGE,
)

DATA = Path(__file__).resolve().parent.parent / "data"


def _norm(text: str) -> str:
    return text.strip().casefold()


def _build_alias_string(old_nom: str, canonical_nom: str, canonical_aliases: str) -> str:
    parts: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        v = value.strip()
        if not v:
            return
        key = v.casefold()
        if key not in seen:
            seen.add(key)
            parts.append(v)

    if _norm(old_nom) != _norm(canonical_nom):
        add(old_nom)
    for piece in canonical_aliases.split("|"):
        add(piece)
    return "|".join(parts)


def normalize_destinations() -> list[dict[str, str]]:
    rows = list(csv.DictReader((DATA / "destinations.csv").open(encoding="utf-8")))
    out: list[dict[str, str]] = []

    for row in rows:
        did = row["id"].strip()
        if did in DESTINATION_MERGE:
            continue

        old_nom = (row.get("nom") or "").strip()
        if did in DESTINATION_CANONICAL:
            nom, pays, aliases = DESTINATION_CANONICAL[did]
            alias_str = _build_alias_string(old_nom, nom, aliases)
        else:
            nom = old_nom
            pays = (row.get("pays") or "").strip()
            alias_str = (row.get("aliases") or "").strip()

        out.append(
            {
                "id": did,
                "nom": nom,
                "pays": pays,
                "region": (row.get("region") or "").strip(),
                "aliases": alias_str,
                "description": f"Activités touristiques à {nom}",
                "saison_ideale": (row.get("saison_ideale") or "").strip(),
            }
        )

    out.sort(key=lambda r: r["nom"].casefold())
    return out


def merge_activities() -> tuple[int, list[dict[str, str]]]:
    rows = list(csv.DictReader((DATA / "activities.csv").open(encoding="utf-8")))
    fieldnames = list(rows[0].keys()) if rows else []
    merged_count = 0

    for row in rows:
        did = row["destination_id"].strip()
        if did in DESTINATION_MERGE:
            row["destination_id"] = DESTINATION_MERGE[did]
            merged_count += 1

    return merged_count, rows, fieldnames


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    dest_rows = normalize_destinations()
    merged_count, act_rows, act_fields = merge_activities()

    write_csv(DATA / "destinations.csv", DESTINATION_FIELDS, dest_rows)
    write_csv(DATA / "activities.csv", act_fields, act_rows)

    print(f"destinations.csv : {len(dest_rows)} lignes")
    print(f"activities.csv   : {len(act_rows)} lignes ({merged_count} fusionnées)")
    for src, tgt in DESTINATION_MERGE.items():
        print(f"  fusion {src} -> {tgt} : {merged_count} activités")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
