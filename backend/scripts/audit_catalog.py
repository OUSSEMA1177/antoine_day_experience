#!/usr/bin/env python3
"""Audit cohérence destinations.csv <-> activities.csv."""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.catalog_normalization import DESTINATION_CANONICAL, DESTINATION_MERGE

DATA = Path(__file__).resolve().parent.parent / "data"


def _norm(text: str) -> str:
    return (text or "").strip().casefold()


def main() -> int:
    dest_rows = list(csv.DictReader((DATA / "destinations.csv").open(encoding="utf-8")))
    act_rows = list(csv.DictReader((DATA / "activities.csv").open(encoding="utf-8")))

    dest_by_id = {r["id"]: r for r in dest_rows}
    counts = Counter(r["destination_id"] for r in act_rows)

    print("=== ACTIVITÉS PAR DESTINATION ===")
    for did, count in sorted(counts.items(), key=lambda x: -x[1]):
        nom = dest_by_id.get(did, {}).get("nom", "?")
        pays = dest_by_id.get(did, {}).get("pays", "")
        print(f"  {did:>8}  {count:>4}  {nom}  [{pays}]")

    orphan_ids = [d for d in counts if d not in dest_by_id]
    if orphan_ids:
        print("\n!!! ORPHELINS (activités sans destination):")
        for d in orphan_ids:
            print(f"  {d}: {counts[d]} activités")

    empty_dest = [r for r in dest_rows if counts.get(r["id"], 0) == 0]
    if empty_dest:
        print("\n!!! DESTINATIONS SANS ACTIVITÉ:")
        for r in empty_dest:
            print(f"  {r['id']} {r['nom']}")

    print("\n=== PAYS MANQUANTS ===")
    missing_pays = [r for r in dest_rows if not (r.get("pays") or "").strip()]
    for r in missing_pays:
        print(f"  {r['id']} {r['nom']}")

    print("\n=== ALIAS MANQUANTS (nom monument vs ville attendue) ===")
    for did, (nom, pays, aliases) in DESTINATION_CANONICAL.items():
        row = dest_by_id.get(did)
        if not row:
            continue
        if _norm(row.get("nom")) != _norm(nom):
            print(f"  {did}: csv='{row.get('nom')}' -> attendu '{nom}'")
        if not (row.get("pays") or "").strip():
            print(f"  {did}: pays vide (attendu '{pays}')")

    merge_pending = [d for d in DESTINATION_MERGE if d in dest_by_id]
    if merge_pending:
        print("\n=== FUSIONS EN ATTENTE ===")
        for src, tgt in DESTINATION_MERGE.items():
            if src in dest_by_id:
                print(f"  {src} ({counts.get(src, 0)} act.) -> {tgt} ({counts.get(tgt, 0)} act.)")

    # Mots-villes fréquents dans titres vs nom destination
    city_re = re.compile(
        r"\b(paris|marrakech|séville|seville|milan|amsterdam|londres|london|"
        r"grenade|granada|naples|tokyo|caire|cairo|cracovie|krakow)\b",
        re.I,
    )
    mismatches: dict[str, set[str]] = defaultdict(set)
    for r in act_rows:
        did = r["destination_id"]
        dest_nom = _norm(dest_by_id.get(did, {}).get("nom", ""))
        titre = r.get("titre", "")
        for m in city_re.findall(titre):
            word = _norm(m)
            if word not in dest_nom and word not in _norm(dest_by_id.get(did, {}).get("aliases", "")):
                mismatches[did].add(m)

    if mismatches:
        print("\n=== TITRES MENTIONNENT UNE VILLE != NOM DESTINATION ===")
        for did, words in sorted(mismatches.items()):
            print(f"  {did} {dest_by_id.get(did, {}).get('nom')}: {', '.join(sorted(words))}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
