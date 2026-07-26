"""Tests quote state et sélection catalogue."""

from agent.context_manager import sync_slots_from_message
from memory.conversation_manager import conversation_manager
from memory.memory_manager import memory_manager
from memory.quote_state import (
    compute_quote_state,
    detect_destination_in_message,
    is_quote_confirmation,
    match_activities_by_titles,
    save_proposed_activities,
    sync_activity_feedback_from_message,
)
from services.data_loader import data_loader


def test_plan_couple_sets_marrakech() -> None:
    session = "plan-couple"
    sync_slots_from_message(session, "fais moi un plan a ton choix juste pour un couple")
    slots = memory_manager.get_slots(session)
    assert slots.get("profil_voyageur") == "couple"
    assert slots.get("destination") == "Marrakech"


def test_tous_sets_envies() -> None:
    session = "tous-envies"
    sync_slots_from_message(session, "tous")
    assert "culture" in str(memory_manager.get_slots(session).get("envies", ""))


def test_agency_name_slot() -> None:
    session = "agency"
    sync_slots_from_message(session, "sousou voyage")
    assert memory_manager.get_slots(session).get("nom_agence") == "Sousou Voyage"


def test_quote_ready_after_proposal_and_confirm() -> None:
    session = "quote-ready"
    memory_manager.update_slots(
        session,
        destination="Marrakech",
        profil_voyageur="couple",
        envies="culture, aventure",
        nom_agence="Sousou Voyage",
    )
    rows = data_loader.search_activities_smart(destination_name="Marrakech", limit=4)[0]
    save_proposed_activities(session, rows)
    memory_manager.update_slots(session, activites_selectionnees=rows[0]["id"])

    state = compute_quote_state(session)
    assert state["quote_ready"] is True
    assert len(state["activities"]) >= 1


def test_detect_zanzibar_destination() -> None:
    assert detect_destination_in_message("j ai aime zanzibar") == "Zanzibar"


def test_reject_activity_removes_from_quote() -> None:
    session = "reject-aquarium"
    memory_manager.update_slots(
        session,
        destination="Zanzibar",
        profil_voyageur="famille",
        nom_agence="Test Agence",
        activites_proposees="54117,61097",
    )
    sync_activity_feedback_from_message(
        session,
        "j ai pas aime Aquarium de Baraka",
    )
    state = compute_quote_state(session)
    assert state["quote_ready"] is False
    assert all("Baraka" not in a["titre"] for a in state["activities"])


def test_select_activity_and_filter_dubai() -> None:
    session = "select-kuza"
    memory_manager.update_slots(
        session,
        destination="Zanzibar",
        profil_voyageur="famille",
        partner_id="1",
        activites_proposees="54117,61097,50333,74136",
    )
    sync_activity_feedback_from_message(session, "j ai pas aime Aquarium de Baraka")
    conversation_manager.add_turn(
        session,
        "alternatives",
        "1. Visite de la grotte de Kuza, lagon bleu — 141,04€",
    )
    sync_activity_feedback_from_message(session, "oui j ai aime ca")

    state = compute_quote_state(session)
    assert state["quote_ready"] is True
    assert len(state["activities"]) == 1
    assert "Kuza" in state["activities"][0]["titre"]
    assert state["destination"] == "Zanzibar"


def test_is_quote_confirmation() -> None:
    assert is_quote_confirmation("oui") is True
    assert is_quote_confirmation("oui c est bon") is True
    assert is_quote_confirmation("j ai dit c est bon a les activites ?") is True
    assert is_quote_confirmation("oui j ai aime ca") is False
    assert is_quote_confirmation("oui ajoute ceci") is False
    assert is_quote_confirmation("la deusieme et je veux une autre activite") is False


def test_wants_another_and_add_this_helpers() -> None:
    from memory.quote_state import is_add_this_activity, is_wants_another_activity

    assert is_wants_another_activity("la deusieme et je veux une autre activite")
    assert is_wants_another_activity("encore une autre activite avec elle")
    assert is_add_this_activity("oui ajoute ceci")
    assert is_add_this_activity("ajoute ca")
    assert is_add_this_activity("non je veux ajouter 6")
    assert is_add_this_activity("ajoute 6")
    assert is_add_this_activity("ajouter la 6")
    assert is_add_this_activity("ajouter 6 aussi")
    assert is_add_this_activity("ajouter lactivite 6")
    assert not is_add_this_activity("oui c est bon")
    assert not is_wants_another_activity("juste les deux premiers")


def test_parse_one_and_six_indices() -> None:
    from memory.quote_state import parse_presentation_indices

    assert parse_presentation_indices("1 et 6") == [1, 6]
    assert parse_presentation_indices("non 1 et 6") == [1, 6]
    assert parse_presentation_indices("non je veux ajouter 6") == [6]
    assert parse_presentation_indices("ajouter 6 aussi") == [6]
    assert parse_presentation_indices("1") == [1]
    assert parse_presentation_indices("ajouter lactivite 6") == [6]


def test_add_this_appends_to_selection() -> None:
    from services.data_loader import data_loader

    a = data_loader.get_activity_by_id("53286")
    b = data_loader.get_activity_by_id("54685")
    assert a and b
    dest = data_loader.get_destination_by_id(a["destination_id"])
    dest_name = (dest or {}).get("nom") or "Séville"

    session = "add-this-append"
    memory_manager.update_slots(
        session,
        destination=dest_name,
        profil_voyageur="couple",
        partner_id="1",
        nom_agence="Test",
        activites_selectionnees="53286",
        activites_proposees="53286,54685",
        activites_discutees="53286,54685",
    )
    conversation_manager.add_turn(
        session,
        "autre theme",
        f"1. **{b['titre']}** — 80 €",
    )
    sync_activity_feedback_from_message(session, "oui ajoute ceci")
    selected = [
        x
        for x in str(memory_manager.get_slots(session).get("activites_selectionnees", "")).split(",")
        if x.strip()
    ]
    assert selected == ["53286", "54685"]

def test_select_four_activities_by_numbered_list() -> None:
    session = "four-activities"
    memory_manager.update_slots(
        session,
        destination="Zanzibar",
        profil_voyageur="famille",
        partner_id="1",
    )
    msg = (
        "non pour ces "
        "1. **Visite de la grotte de Kuza, lagon bleu, aventure des étoiles de mer, "
        "restaurant The Rock, plage de Paje** pour 141.04€. "
        "2. **Journée sur l'île de la prison et la plage de Nakupenda Sandbank** pour 193.50€. "
        "3. **Forêt de Jozani, visite du village et plage de Mtende Zanzibar** pour 102.34€. "
        "4. **Visite des dauphins, grotte de Kuza, plage de Paje et Forêt de Jozani** pour 123.84€"
    )
    sync_activity_feedback_from_message(session, msg)

    state = compute_quote_state(session)
    assert state["quote_ready"] is True
    assert len(state["activities"]) == 4
    ids = {a["id"] for a in state["activities"]}
    assert ids == {"61097", "58235", "58238", "61082"}


def test_match_four_titles_from_catalog() -> None:
    text = (
        "1. Visite de la grotte de Kuza, lagon bleu, aventure des étoiles de mer\n"
        "2. Journée sur l'île de la prison et la plage de Nakupenda Sandbank\n"
        "3. Forêt de Jozani, visite du village et plage de Mtende Zanzibar\n"
        "4. Visite des dauphins, grotte de Kuza, plage de Paje et Forêt de Jozani"
    )
    ids = match_activities_by_titles(text, "Zanzibar")
    assert len(ids) == 4
    assert set(ids) == {"61097", "58235", "58238", "61082"}


def test_select_all_discussed() -> None:
    session = "all-discussed"
    memory_manager.update_slots(
        session,
        destination="Zanzibar",
        profil_voyageur="famille",
        partner_id="1",
        activites_discutees="61097,58235,58238,61082",
    )
    sync_activity_feedback_from_message(
        session,
        "oui je veux toutes les activites qu on a discute",
    )
    state = compute_quote_state(session)
    assert len(state["activities"]) == 4


def test_confirm_single_activity_from_last_presentation() -> None:
    """Bali : 7 activités en slots mais 1 seule présentée → confirmation = 1 activité."""
    session = "bali-single"
    memory_manager.update_slots(
        session,
        destination="Bali",
        profil_voyageur="groupe",
        taille_groupe="8",
        envies="aventure",
        partner_id="1",
        nom_agence="TUI Test",
        activites_discutees="14650,62826,63644,62843,62341,62339,63632",
        activites_proposees="14650,62826,63644,62843",
    )
    conversation_manager.add_turn(
        session,
        "budget",
        (
            "Malheureusement, je n'ai qu'une seule activité dans mon catalogue pour Bali. "
            "Puis-je générer un devis pour cette activité ?\n"
            "1. Forêt tropicale de Bali en 4X4 : visite en petit groupe - 107,50€"
        ),
    )
    sync_activity_feedback_from_message(session, "oui c est bon")

    state = compute_quote_state(session)
    assert state["quote_ready"] is True
    assert len(state["activities"]) == 1
    assert state["activities"][0]["id"] == "14650"
    assert "4X4" in state["activities"][0]["titre"]


def test_correction_non_juste_replaces_selection() -> None:
    """« non juste [titre] » remplace la sélection erronée."""
    session = "bali-correction"
    memory_manager.update_slots(
        session,
        destination="Bali",
        profil_voyageur="groupe",
        partner_id="1",
        nom_agence="TUI Test",
        activites_selectionnees="14650,62826,63644,62843,62341,62339,63632",
    )
    sync_activity_feedback_from_message(
        session,
        "non juste . Forêt tropicale de Bali en 4X4 : visite en petit groupe - 107,50€",
    )

    state = compute_quote_state(session)
    assert len(state["activities"]) == 1
    assert state["activities"][0]["id"] == "14650"


def test_parse_premier_et_quatrieme_indices() -> None:
    from memory.quote_state import parse_presentation_indices

    assert parse_presentation_indices("le premier et le quatrieme j ai aime") == [1, 4]
    assert parse_presentation_indices("non c est juste le premier et le quatrieme") == [1, 4]
    assert parse_presentation_indices("le rpemier et le quatrieme") == [1, 4]
    assert parse_presentation_indices("1 et 4") == [1, 4]


def test_parse_deusieme_typo_and_les_deux_not_select_all() -> None:
    from memory.quote_state import parse_presentation_indices

    assert parse_presentation_indices("la deusieme et la troisieme sont bonnes") == [2, 3]
    assert parse_presentation_indices(
        "non les deux la troisieme et la deusieme j ai dit"
    ) == [2, 3]
    assert parse_presentation_indices("les deux") == [1, 2]
    assert parse_presentation_indices("je veux les trois") == [1, 2, 3]
    assert parse_presentation_indices("juste les deux premiers") == [1, 2]
    assert parse_presentation_indices("les deux premiers") == [1, 2]
    assert parse_presentation_indices("les 3 premiers") == [1, 2, 3]
    assert parse_presentation_indices("les trois premiers") == [1, 2, 3]


def test_select_deuxieme_troisieme_with_typos() -> None:
    """« deusieme et troisieme » / correction « les deux » → indices 2 et 3 uniquement."""
    session = "ordinal-typo-caire"
    ids = ["a1", "a2", "a3", "a4"]
    memory_manager.update_slots(
        session,
        destination="Le Caire",
        profil_voyageur="groupe_amis",
        partner_id="1",
        nom_agence="TUI Test",
        activites_proposees=",".join(ids),
        activites_discutees=",".join(ids),
    )
    from memory import quote_state as qs

    original = qs._last_presentation_activities
    qs._last_presentation_activities = lambda _sid: list(ids)
    try:
        sync_activity_feedback_from_message(
            session, "la deusieme et la troisieme sont bonnes"
        )
        selected = str(
            memory_manager.get_slots(session).get("activites_selectionnees", "")
        )
        assert selected.split(",") == ["a2", "a3"]

        sync_activity_feedback_from_message(
            session, "non les deux la troisieme et la deusieme j ai dit"
        )
        selected = str(
            memory_manager.get_slots(session).get("activites_selectionnees", "")
        )
        assert selected.split(",") == ["a2", "a3"]
    finally:
        qs._last_presentation_activities = original


def test_select_premier_et_quatrieme_from_presentation() -> None:
    """Choix ordinal → uniquement activités #1 et #4 de la dernière présentation."""
    session = "ordinal-select"
    ids = ["72955", "72783", "62077", "72870"]
    memory_manager.update_slots(
        session,
        destination="Le Caire",
        profil_voyageur="couple",
        partner_id="1",
        nom_agence="TUI Test",
        activites_proposees=",".join(ids),
        activites_discutees=",".join(ids),
        activites_selectionnees=",".join(ids),  # mauvaise sélection initiale (les 4)
    )
    conversation_manager.add_turn(
        session,
        "mix",
        (
            "Voici 4 activités :\n"
            "1. Grand musée égyptien : Billet coupe-file – 36,98€\n"
            "2. Visite d'une demi-journée du Grand Musée égyptien – 53,32€\n"
            "3. Excursion d'une journée VIP à l'intérieur des pyramides de Gizeh – 113,52€\n"
            "4. Grand musée égyptien : billet d'entrée avec transferts – 0€"
        ),
    )

    sync_activity_feedback_from_message(
        session, "le premier et le quatrieme j ai aime"
    )
    state = compute_quote_state(session)
    assert [a["id"] for a in state["activities"]] == ["72955", "72870"]

    # Correction après mauvaise sélection
    memory_manager.update_slots(session, activites_selectionnees=",".join(ids))
    sync_activity_feedback_from_message(
        session, "non c est juste le premier et le quatrieme"
    )
    state = compute_quote_state(session)
    assert [a["id"] for a in state["activities"]] == ["72955", "72870"]
    assert state["quote_ready"] is True

