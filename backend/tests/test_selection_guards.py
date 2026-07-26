"""Tests garde-fous : questions ≠ confirm, les trois, faux Asie, ask destination."""

from agent.intent_detector import Intent
from agent.planner import Action, plan_next
from memory.conversation_manager import conversation_manager
from memory.memory_manager import memory_manager
from memory.quote_state import (
    is_clarifying_question,
    is_quote_confirmation,
    parse_presentation_indices,
    sync_activity_feedback_from_message,
)
from search.geo import detect_continent_query, detect_country_query, is_explicit_region_request


def test_clarifying_question_not_selection() -> None:
    assert is_clarifying_question("la premier activite c est a istanbul ?") is True
    assert is_clarifying_question("est ce que cette activite est a Istanbul") is True
    assert is_clarifying_question("la premiere activite c est a istanbul") is True
    assert is_clarifying_question("oui c est parfait") is False
    assert is_clarifying_question("je veux les trois") is False
    assert is_clarifying_question("donner moi un devis des 3 activites") is False


def test_premier_question_does_not_parse_index() -> None:
    assert parse_presentation_indices("la premier activite c est a istanbul ?") == []
    assert parse_presentation_indices("le premier et le quatrieme j ai aime") == [1, 4]


def test_premier_question_does_not_confirm() -> None:
    assert is_quote_confirmation("la premier activite c est a istanbul ?") is False
    assert is_quote_confirmation("oui c est bon") is True


def test_select_all_tous_c_est_bon() -> None:
    from memory.quote_state import SELECT_ALL_RE, sync_activity_feedback_from_message

    assert SELECT_ALL_RE.search("tous c est bon")
    assert SELECT_ALL_RE.search("toutes")
    session = "tous-bon"
    ids = ["a1", "a2", "a3", "a4"]
    memory_manager.update_slots(
        session,
        destination="Paris",
        profil_voyageur="groupe",
        partner_id="1",
        nom_agence="Test",
        activites_proposees=",".join(ids),
        activites_discutees=",".join(ids),
    )
    conversation_manager.add_turn(
        session,
        "culture",
        "1. **A** — 10 €\n2. **B** — 20 €\n3. **C** — 30 €\n4. **D** — 40 €",
    )
    sync_activity_feedback_from_message(session, "tous c est bon")
    selected = str(memory_manager.get_slots(session).get("activites_selectionnees", ""))
    assert set(selected.split(",")) == set(ids)


def test_remove_activity_after_selection() -> None:
    from memory.quote_state import sync_activity_feedback_from_message

    session = "remove-moulin"
    ids = ["x1", "x2"]
    memory_manager.update_slots(
        session,
        destination="Paris",
        profil_voyageur="groupe",
        activites_selectionnees=",".join(ids),
        activites_proposees=",".join(ids),
        activites_discutees=",".join(ids),
    )
    conversation_manager.add_turn(
        session,
        "ok",
        "1. **Moulin Rouge : dîner** — 100 €\n2. **Paradis Latin : dîner** — 80 €",
    )
    # Simuler IDs connus via proposees matching presentation order
    sync_activity_feedback_from_message(
        session, "desole je veux pas la premiere - Moulin Rouge"
    )
    selected = str(memory_manager.get_slots(session).get("activites_selectionnees", ""))
    assert selected == "x2"

    session = "les-trois-istanbul"
    memory_manager.update_slots(
        session,
        destination="Istanbul",
        profil_voyageur="groupe",
        nom_agence="Test Agence",
        partner_id="1",
    )
    # Simuler présentation de 3 activités gastro Istanbul
    conversation_manager.add_turn(
        session,
        "gastronomie",
        "Voici 3 activités :\n"
        "1. **Soirée gastronomie et culture - Dîner au dessert asiatique en Europe** — 115,24 €\n"
        "2. **Istanbul : dîner-croisière avec spectacle et table privée** — 32,68 €\n"
        "3. **Istanbul : dîner croisière sur le Bosphore avec animation** — 72,24 €\n"
        "Souhaitez-vous en sélectionner ?",
    )
    # Mauvaise sélection préalable (bug ordinal)
    memory_manager.update_slots(session, activites_selectionnees="99999")

    sync_activity_feedback_from_message(session, "je veux les trois")
    selected = str(memory_manager.get_slots(session).get("activites_selectionnees", ""))
    ids = [x for x in selected.split(",") if x.strip()]
    assert len(ids) == 3
    assert "99999" not in ids


def test_juste_les_deux_premiers_selects_first_two() -> None:
    """« juste les deux premiers » ≠ lieu « Deux Premiers »."""
    from unittest.mock import MagicMock, patch

    from agent.destination_policy import detect_unknown_place_request
    from agent.orchestrator import orchestrator

    assert detect_unknown_place_request("juste les deux premiers") is None
    assert parse_presentation_indices("juste les deux premiers") == [1, 2]

    session = "deux-premiers-marrakech"
    ids = ["53155", "54878", "54492", "55855"]
    memory_manager.update_slots(
        session,
        destination="Marrakech",
        profil_voyageur="couple",
        nom_agence="Japanticket Inc.",
        partner_id="1",
        activites_proposees=",".join(ids),
        activites_discutees=",".join(ids),
    )
    conversation_manager.add_turn(
        session,
        "mix de tout",
        "1. **Act A** — 10 €\n2. **Act B** — 20 €\n3. **Act C** — 30 €\n4. **Act D** — 40 €",
    )

    mock_settings = MagicMock(
        llm_model="anthropic/claude-haiku-4-5",
        anthropic_api_key="test-key",
        groq_api_key="",
        gemini_api_key="",
        llm_fallback_model="",
        llm_max_tokens=512,
        llm_timeout=90,
        llm_retry_max=0,
        llm_retry_delay=0.1,
        llm_nlu_extract=True,
        llm_log_usage=False,
        llm_history_limit=8,
        llm_catalog_inject_limit=4,
        llm_compact_prompt=True,
    )
    with patch("agent.orchestrator.get_settings", return_value=mock_settings):
        with patch("agent.nlu_extractor.litellm.completion") as mock_nlu:
            reply, _, meta = orchestrator.chat(session, "juste les deux premiers")

    assert "Deux Premiers" not in reply
    assert "prépare" in reply.casefold() or "devis" in reply.casefold()
    assert "Cliquez sur le bouton" not in reply
    selected = str(memory_manager.get_slots(session).get("activites_selectionnees", ""))
    assert "53155" in selected
    assert "54878" in selected
    assert "54492" not in selected
    mock_nlu.assert_not_called()
    assert meta.get("quote_ready") is False
    assert memory_manager.get_slots(session).get("awaiting_quote_confirm") == "1"

def test_devis_des_3_activites_selects_presentation() -> None:
    session = "devis-des-3"
    memory_manager.update_slots(
        session,
        destination="Istanbul",
        profil_voyageur="groupe",
        nom_agence="Test",
    )
    conversation_manager.add_turn(
        session,
        "ok",
        "1. **Istanbul : dîner-croisière avec spectacle et table privée** — 32,68 €\n"
        "2. **Istanbul : dîner croisière sur le Bosphore avec animation** — 72,24 €\n"
        "3. **Soirée gastronomie et culture - Dîner au dessert asiatique en Europe** — 115,24 €",
    )
    sync_activity_feedback_from_message(session, "ok donc donner moi un devis des 3 activites")
    selected = str(memory_manager.get_slots(session).get("activites_selectionnees", ""))
    assert len([x for x in selected.split(",") if x.strip()]) == 3


def test_asiatique_in_title_not_continent() -> None:
    msg = (
        'ajouter Soirée gastronomie et culture - Dîner au dessert asiatique en Europe '
        "est a Istanbu"
    )
    assert detect_continent_query(msg) is None
    assert detect_country_query(msg) is None
    assert is_explicit_region_request(msg) is False


def test_plage_en_asie_still_detected() -> None:
    assert detect_continent_query("plage en asie") == "asie"
    assert detect_country_query("je veux des pays asiatiques") == "asie"
    assert is_explicit_region_request("plage en asie") is True


def test_planner_asks_destination_without_place() -> None:
    plan = plan_next(
        Intent.TUNNEL_QUALIFY,
        {"taille_groupe": "6", "duree": "3 jours", "profil_voyageur": "groupe"},
        has_catalog_results=True,
        escalated=False,
    )
    assert plan.action == Action.ASK_DESTINATION


def test_planner_allows_theme_without_destination() -> None:
    plan = plan_next(
        Intent.ACTIVITY_SEARCH,
        {"envies": "mer"},
        has_catalog_results=False,
        escalated=False,
    )
    assert plan.action == Action.SEARCH_CATALOG


def test_select_one_and_six_from_six_item_list() -> None:
    """« 1 et 6 » doit mapper la 1re et la 6e ligne (pas tronquer à 4)."""
    session = "select-1-et-6"
    ids = ["m1", "m2", "m3", "m4", "m5", "m6"]
    memory_manager.update_slots(
        session,
        destination="Miami",
        profil_voyageur="groupe",
        partner_id="1",
        nom_agence="Test",
        activites_proposees=",".join(ids),
        activites_discutees=",".join(ids),
    )
    conversation_manager.add_turn(
        session,
        "miami",
        "\n".join(f"{i}. **Act {i}** — {10 * i} €" for i in range(1, 7)),
    )
    sync_activity_feedback_from_message(session, "1 et 6")
    selected = str(memory_manager.get_slots(session).get("activites_selectionnees", ""))
    assert selected.split(",") == ["m1", "m6"]

    # Correction après mauvaise sélection
    memory_manager.update_slots(session, activites_selectionnees="m1")
    sync_activity_feedback_from_message(session, "non 1 et 6")
    selected = str(memory_manager.get_slots(session).get("activites_selectionnees", ""))
    assert selected.split(",") == ["m1", "m6"]


def test_ajouter_six_after_llm_confirmation_message() -> None:
    """Après un « 1 » LLM, « ajouter 6 aussi » doit append via proposees / liste numérotée."""
    session = "ajouter-6-after-confirm"
    ids = ["m1", "m2", "m3", "m4", "m5", "m6"]
    memory_manager.update_slots(
        session,
        destination="Miami",
        profil_voyageur="groupe",
        partner_id="1",
        activites_selectionnees="m1",
        activites_proposees=",".join(ids),
        activites_discutees=",".join(ids),
    )
    # Liste Miami (numérotée)
    conversation_manager.add_turn(
        session,
        "miami",
        "Voici des activités à Miami :\n"
        + "\n".join(f"{i}. **Act {i}** — {10 * i} €" for i in range(1, 7))
        + "\nLaquelle vous intéresse ?",
    )
    # Réponse LLM après « 1 » — ne doit PAS écraser la liste pour l'index 6
    conversation_manager.add_turn(
        session,
        "1",
        "Compris. Activité sélectionnée : **Act 1** — 10 € (net). "
        "Je prépare le devis pour votre groupe de 5 ?",
    )
    from memory.quote_state import is_add_this_activity, parse_presentation_indices

    assert is_add_this_activity("ajouter 6 aussi")
    assert parse_presentation_indices("ajouter 6 aussi") == [6]
    assert parse_presentation_indices("1") == [1]
    assert is_add_this_activity("ajouter lactivite 6")

    sync_activity_feedback_from_message(session, "ajouter 6 aussi")
    selected = str(memory_manager.get_slots(session).get("activites_selectionnees", ""))
    assert selected.split(",") == ["m1", "m6"]


def test_save_proposed_replaces_not_appends() -> None:
    from memory.quote_state import save_proposed_activities

    session = "propose-replace"
    memory_manager.update_slots(session, destination="Miami", activites_proposees="old1,old2")
    save_proposed_activities(
        session,
        [{"id": "n1", "destination_id": "x"}, {"id": "n2", "destination_id": "x"}],
    )
    # Sans filtre destination match, peut être vide — forcer via update si filtre
    # Utiliser des IDs réels Miami si possible ; sinon set proposees manuellement après
    from services.data_loader import data_loader

    rows = data_loader.search_activities_smart(destination_name="Miami", limit=3)[0]
    if not rows:
        return
    memory_manager.update_slots(session, destination="Miami", activites_proposees="old1,old2")
    new_ids = save_proposed_activities(session, rows)
    proposees = str(memory_manager.get_slots(session).get("activites_proposees", ""))
    assert "old1" not in proposees
    assert proposees == ",".join(new_ids)
