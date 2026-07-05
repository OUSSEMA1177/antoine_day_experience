"""Structured session slots (destination, budget, profil…)."""

from __future__ import annotations

from memory.session_store import session_store

SLOT_KEYS = (
    "destination",
    "dates",
    "duree",
    "profil_voyageur",
    "premiere_visite",
    "envies",
    "budget",
    "taille_groupe",
    "destinations_exclues",
    "partner_id",
    "nom_agence",
    "preference",
    "activites_proposees",
    "activites_selectionnees",
    "activites_rejetees",
    "activites_discutees",
    "devis_ref",
    "validite_jours",
)


class MemoryManager:
    def get_slots(self, session_id: str) -> dict[str, str | list[str]]:
        return session_store.get(session_id).slots

    def update_slots(self, session_id: str, **kwargs: str | list[str] | None) -> None:
        slots = session_store.get(session_id).slots
        for key, value in kwargs.items():
            if key not in SLOT_KEYS or value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            slots[key] = value

    def clear_slot(self, session_id: str, key: str) -> None:
        slots = session_store.get(session_id).slots
        slots.pop(key, None)

    def add_excluded_destination(self, session_id: str, place: str) -> None:
        slots = session_store.get(session_id).slots
        current = str(slots.get("destinations_exclues", "") or "")
        parts = [p.strip() for p in current.split(",") if p.strip()]
        if place.strip() and place.strip() not in parts:
            parts.append(place.strip())
        slots["destinations_exclues"] = ", ".join(parts)

    def get_excluded_destinations(self, session_id: str) -> list[str]:
        raw = str(self.get_slots(session_id).get("destinations_exclues", "") or "")
        return [p.strip() for p in raw.split(",") if p.strip()]

    def mark_escalated(self, session_id: str) -> None:
        session_store.get(session_id).escalated = True

    def is_escalated(self, session_id: str) -> bool:
        return session_store.get(session_id).escalated

    def context_summary(self, session_id: str) -> str:
        slots = self.get_slots(session_id)
        if not slots:
            return "Aucune information mémorisée pour cette session."

        labels = {
            "destination": "Destination",
            "dates": "Dates",
            "duree": "Durée",
            "profil_voyageur": "Profil voyageur",
            "premiere_visite": "Première visite",
            "envies": "Envies",
            "budget": "Budget",
            "taille_groupe": "Taille du groupe",
            "destinations_exclues": "Destinations exclues",
            "partner_id": "Agence partenaire",
            "nom_agence": "Nom agence (white label)",
            "preference": "Préférence prestation",
            "activites_proposees": "Activités proposées (catalogue)",
            "activites_selectionnees": "Activités sélectionnées",
            "activites_discutees": "Activités discutées",
            "devis_ref": "Référence devis",
            "validite_jours": "Validité devis (jours)",
        }
        lines = []
        for key, label in labels.items():
            if key in slots and slots[key]:
                lines.append(f"- {label} : {slots[key]}")
        return "\n".join(lines) if lines else "Aucune information mémorisée pour cette session."


memory_manager = MemoryManager()
