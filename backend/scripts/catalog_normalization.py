"""Mapping canonique destinations — villes, pays, alias B2B."""

from __future__ import annotations

# destination_id -> (nom, pays, aliases pipe-separated)
# aliases : anciens noms B2B + synonymes utilisateur
DESTINATION_CANONICAL: dict[str, tuple[str, str, str]] = {
    "3114": ("Athènes", "Grèce", ""),
    "3471": ("Bali", "Indonésie", ""),
    "1219": ("Barcelone", "Espagne", ""),
    "3416": ("Budapest", "Hongrie", ""),
    "202467": ("Foz do Iguaçu", "Brésil", "Chutes d'Iguaçu|Iguaçu|Iguazu"),
    "261": ("Dubaï", "Émirats arabes unis", "Dubai"),
    "4172": ("Milan", "Italie", "Duomo de Milan"),
    "4860": ("Marrakech", "Maroc", "Désert d'Agafay|Agafay|marrakch"),
    "651": ("Île de Pâques", "Chili", "Ile de Pâques (13)"),
    "9693": ("Istanbul", "Turquie", ""),
    "1138": ("Le Caire", "Égypte", "Caire|Cairo|Grand Musée égyptien|Gizeh|Pyramides"),
    "5681": ("Lisbonne", "Portugal", ""),
    "185168": ("Malte", "Malte", ""),
    "7777": ("Miami", "États-Unis", ""),
    "203137": ("Pétra", "Jordanie", "Monastère de Pétra|Petra"),
    "4717": ("Tokyo", "Japon", "Mont Fuji|Fuji"),
    "560": ("Montréal", "Canada", ""),
    "5572": ("Cracovie", "Pologne", "Musée national Auschwitz-Birkenau|Auschwitz|Oświęcim|Kraków|Krakow"),
    "5113": ("Amsterdam", "Pays-Bas", "Musée Van Gogh"),
    "8067": ("New York", "États-Unis", "NYC"),
    "8842": ("Séville", "Espagne", "Palais Alcazar de Séville|Alcazar|Seville"),
    "1366": ("Grenade", "Espagne", "Granada|Alhambra|Palais nasrides de l'Alhambra"),
    "7502": ("Grand Canyon", "États-Unis", "Parc National Grand Canyon"),
    "203298": ("Parc Kruger", "Afrique du Sud", "Parc national Kruger|Kruger"),
    "2222": ("Paris", "France", ""),
    "8262": ("Pékin", "Chine", "Beijing"),
    "660": ("Puerto Natales", "Chili", "Puerto Natales (37)"),
    "661": ("Punta Arenas", "Chili", "Punta Arenas (8)"),
    "395": ("Rio de Janeiro", "Brésil", "Rio"),
    "4362": ("Rome", "Italie", "Roma"),
    "4213": ("Naples", "Italie", "Pompéi|Pompei|Ruines de Pompéi"),
    "669": ("San Pedro de Atacama", "Chili", "San Pedro De Atacama (9)|Atacama"),
    "667": ("Santiago", "Chili", "Santiago (4)"),
    "3227": ("Santorin", "Grèce", "Santorini"),
    "2797": ("Londres", "Royaume-Uni", "London|Studios Warner Bros|Warner Bros"),
    "201717": ("Tulum", "Mexique", ""),
    "202185": ("Valparaíso", "Chili", "Valparaiso (17)"),
    "4497": ("Venise", "Italie", "Venezia"),
    "9632": ("Vienne", "Autriche", "Wien"),
    "9538": ("Zanzibar", "Tanzanie", ""),
}

# Fusion : ancien destination_id -> id canonique
DESTINATION_MERGE: dict[str, str] = {
    "202816": "1138",  # Grand Musée égyptien -> Le Caire
}

DESTINATION_FIELDS = ["id", "nom", "pays", "region", "aliases", "description", "saison_ideale"]
